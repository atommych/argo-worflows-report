import os
import sys
import json
import logging
import argparse
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import requests
import pandas as pd
import plotly.express as px
import plotly.offline
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
class Config:
    """Configuration class for Argo workflow reporting."""

    def __init__(self):
        self.api_url = os.getenv('ARGO_API_URL','')
        self.bearer_token = os.getenv('ARGO_BEARER_TOKEN', '')
        self.namespace = os.getenv('ARGO_NAMESPACE', 'default')
        self.workflow_limit = int(os.getenv('ARGO_WORKFLOW_LIMIT', '1000'))
        self.output_file = None  # Will be set dynamically

        # S3 Configuration
        self.s3_bucket = os.getenv('S3_BUCKET', '')
        self.s3_prefix = os.getenv('S3_PREFIX', 'argo-reports/')
        self.s3_region = os.getenv('AWS_REGION', 'eu-central-1')

    def get_headers(self) -> Dict[str, str]:
        """Build request headers."""
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers

    def build_url(self, phase: str = 'Succeeded') -> str:
        """Build the API URL with query parameters."""
        return (
            f"{self.api_url}?"
            f"listOptions.labelSelector=workflows.argoproj.io/phase={phase}&"
            f"listOptions.limit={self.workflow_limit}"
        )

    def generate_output_filename(
        self,
        start_date: datetime,
        phase: str = 'Succeeded',
        days: int = 1,
        custom_output: Optional[str] = None
    ) -> str:
        """
        Generate dynamic output filename based on parameters.

        Args:
            start_date: Start date of the report
            phase: Workflow phase filter
            days: Number of days in the report
            custom_output: Custom output filename (overrides auto-generation)

        Returns:
            Generated filename string
        """
        if custom_output:
            return custom_output

        # Format: argo_wfs_YYYY_MM_DD[_status_phase][_days_N].html
        date_str = start_date.strftime('%Y_%m_%d')
        parts = ['argo_wfs', date_str]

        # Add phase if not the default "Succeeded"
        if phase.lower() != 'succeeded':
            parts.append(f'status_{phase.lower()}')

        # Add days if more than 1
        if days > 1:
            parts.append(f'days_{days}')

        # If it's just the default (single day, succeeded), add 'full'
        if len(parts) == 2:
            parts.append('full')

        filename = '_'.join(parts) + '.html'
        return filename

TERM_DEF = {
    'run': 'metadata.name',
    'owner_kind': 'metadata.ownerReferences.kind',
    'owner_name': 'metadata.ownerReferences.name',
    'parameters': 'spec.arguments',
    'status': 'status.phase',
    'start_time': 'status.startedAt',
    'end_time': 'status.finishedAt',
    'cpu': 'status.resourcesDuration.cpu',
    'mem': 'status.resourcesDuration.memory',
    'service_account_name': 'status.storedWorkflowTemplateSpec.serviceAccountName'
}


def get_value_from_obj(data_obj: Any, part: str) -> Any:
    """
    Gets the value from the given object at the specified path part.

    Args:
        data_obj: A Python object (dict or list).
        part: A string key to extract from the object.

    Returns:
        The value at the specified path, or None if the value does not exist.
    """
    if isinstance(data_obj, dict):
        return data_obj.get(part)
    elif isinstance(data_obj, list):
        # If the current part is a list, gather all values into a list
        values = [item.get(part) for item in data_obj if isinstance(item, dict)]
        return values if values else None
    return None


def json_to_df(json_data: Dict[str, Any]) -> pd.DataFrame:
    """
    Convert Argo workflow JSON data to a pandas DataFrame.

    Args:
        json_data: JSON data from Argo API containing workflow items.

    Returns:
        DataFrame with flattened workflow data.
    """
    if 'items' not in json_data:
        logger.warning("No 'items' key found in JSON data")
        return pd.DataFrame()

    flat_table = []
    for term in json_data['items']:
        row = {}
        for output_field, input_path in TERM_DEF.items():
            input_path_parts = input_path.split('.')
            value = term

            # Navigate through nested structure
            for part in input_path_parts:
                value = get_value_from_obj(value, part)
                if value is None:
                    break

            # Clean string values
            if isinstance(value, str):
                value = value.replace('\n', ' ')

            row[output_field] = value
        flat_table.append(row)

    return pd.DataFrame(flat_table)


def fetch_workflows(config: Config, phase: str = 'Succeeded') -> Optional[Dict[str, Any]]:
    """
    Fetch workflows from Argo API.

    Args:
        config: Configuration object.
        phase: Workflow phase to filter (default: 'Succeeded').

    Returns:
        JSON response data or None if request fails.
    """
    url = config.build_url(phase)
    headers = config.get_headers()

    try:
        logger.info(f"Fetching workflows from {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching workflows: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON response: {e}")
        return None


def process_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Process the workflow DataFrame by adding computed columns.

    Args:
        df: Raw workflow DataFrame.

    Returns:
        Processed DataFrame with additional columns.
    """
    if df.empty:
        logger.warning("Empty DataFrame, skipping processing")
        return df

    # Extract workflow name (remove random suffix)
    df['workflow'] = df['run'].apply(
        lambda v: '-'.join(v.split('-')[:-1]) if pd.notna(v) and v else None
    )

    # Parse datetime columns with error handling
    df['start_date'] = pd.to_datetime(df['start_time'], format='%Y-%m-%dT%H:%M:%SZ', errors='coerce')
    df['end_date'] = pd.to_datetime(df['end_time'], format='%Y-%m-%dT%H:%M:%SZ', errors='coerce')

    # Calculate time of day (timedelta from midnight)
    df['start_time_of_day'] = df['start_date'] - df['start_date'].dt.normalize()
    df['end_time_of_day'] = df['end_date'] - df['end_date'].dt.normalize()

    # Calculate duration
    df['duration'] = df['end_date'] - df['start_date']
    df['duration_seconds'] = df['duration'].dt.total_seconds()

    return df


def filter_by_date_range(
    df: pd.DataFrame,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
) -> pd.DataFrame:
    """
    Filter DataFrame by date range.

    Args:
        df: Workflow DataFrame.
        start_date: Start date (default: today at midnight).
        end_date: End date (default: tomorrow at midnight).

    Returns:
        Filtered DataFrame.
    """
    if df.empty:
        return df

    if start_date is None:
        start_date = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    if end_date is None:
        end_date = (datetime.today() + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

    logger.info(f"Filtering workflows between {start_date} and {end_date}")

    mask = (df['start_date'] >= start_date) & (df['start_date'] < end_date)
    filtered_df = df[mask].copy()
    filtered_df.sort_values(by='start_time_of_day', inplace=True)

    logger.info(f"Found {len(filtered_df)} workflows in date range")
    return filtered_df


def create_timeline_chart(df: pd.DataFrame, output_file: str) -> None:
    """
    Create and save a timeline chart of workflows.

    Args:
        df: Filtered workflow DataFrame.
        output_file: Output HTML file path.
    """
    if df.empty:
        logger.warning("No data to plot")
        return

    logger.info(f"Creating timeline chart with {len(df)} workflows")

    fig = px.timeline(
        df,
        x_start="start_date",
        x_end="end_date",
        y="workflow",
        hover_data=['run', 'duration_seconds', 'status'],
        title="Argo Workflow Timeline"
    )

    fig.update_yaxes(autorange="reversed")  # Tasks listed from top to bottom
    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Workflow",
        height=max(400, len(df['workflow'].unique()) * 30)  # Dynamic height
    )

    plotly.offline.plot(fig, filename=output_file, auto_open=False)
    logger.info(f"Timeline chart saved to {output_file}")


def print_summary_stats(df: pd.DataFrame) -> None:
    """Print summary statistics of workflows."""
    if df.empty:
        return

    print("\n" + "="*60)
    print("WORKFLOW SUMMARY STATISTICS")
    print("="*60)
    print(f"Total workflows: {len(df)}")
    print(f"Unique workflows: {df['workflow'].nunique()}")
    print(f"\nDuration Statistics:")
    print(f"  Average: {df['duration_seconds'].mean():.2f}s")
    print(f"  Median: {df['duration_seconds'].median():.2f}s")
    print(f"  Min: {df['duration_seconds'].min():.2f}s")
    print(f"  Max: {df['duration_seconds'].max():.2f}s")
    print("\nTop 5 longest running workflows:")
    top_5 = df.nlargest(5, 'duration_seconds')[['workflow', 'run', 'duration_seconds']]
    print(top_5.to_string(index=False))
    print("="*60 + "\n")


def upload_to_s3(file_path: str, bucket: str, object_name: str, config: Config) -> None:
    """
    Upload a file to an S3 bucket.

    Args:
        file_path: File to upload.
        bucket: Bucket to upload to.
        object_name: S3 object name.
        config: Configuration object.

    Raises:
        ValueError: If the bucket name is not specified.
    """
    if not bucket:
        raise ValueError("Bucket name must be specified for S3 upload")

    # If S3_PREFIX is set, prepend it to the object name
    if config.s3_prefix and not object_name.startswith(config.s3_prefix):
        object_name = f"{config.s3_prefix}{object_name}"

    # Upload the file with proper content type for HTML
    try:
        s3_client = boto3.client('s3', region_name=config.s3_region)
        extra_args = {
            'ContentType': 'text/html',
            'CacheControl': 'max-age=300'
        }
        s3_client.upload_file(file_path, bucket, object_name, ExtraArgs=extra_args)

        # Generate the public URL
        s3_url = f"https://{bucket}.s3.{config.s3_region}.amazonaws.com/{object_name}"
        logger.info(f"File uploaded successfully!")
        logger.info(f"S3 URI: s3://{bucket}/{object_name}")
        logger.info(f"Public URL: {s3_url}")
    except FileNotFoundError:
        logger.error(f"The file was not found: {file_path}")
        raise
    except NoCredentialsError:
        logger.error("AWS credentials not found")
        raise
    except ClientError as e:
        logger.error(f"Failed to upload file to S3: {e}")
        raise


def main():
    """Main function to orchestrate the workflow report generation."""
    parser = argparse.ArgumentParser(
        description='Generate Argo Workflow reports and timeline visualizations'
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Specific date to report on (format: YYYY-MM-DD). Default is today.'
    )
    parser.add_argument(
        '--phase',
        type=str,
        default='Succeeded',
        choices=['Succeeded', 'Failed', 'Running', 'Pending'],
        help='Workflow phase to filter (default: Succeeded)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output HTML file path'
    )
    parser.add_argument(
        '--token',
        type=str,
        help='Bearer token for authentication (or set ARGO_BEARER_TOKEN env var)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=1,
        help='Number of days to include in report (default: 1)'
    )
    parser.add_argument(
        '--workflow',
        type=str,
        help='Filter by workflow name (supports regex patterns)'
    )

    args = parser.parse_args()

    # Initialize configuration
    config = Config()

    # Override with command-line arguments
    if args.token:
        config.bearer_token = args.token

    # Validate token
    if not config.bearer_token:
        logger.warning(
            "No bearer token provided. Set ARGO_BEARER_TOKEN environment variable "
            "or use --token argument for authenticated requests."
        )

    # Fetch workflows
    argo_report = fetch_workflows(config, phase=args.phase)
    if not argo_report:
        logger.error("Failed to fetch workflows. Exiting.")
        sys.exit(1)

    # Convert to DataFrame
    df_wf = json_to_df(argo_report)
    if df_wf.empty:
        logger.error("No workflow data found. Exiting.")
        sys.exit(1)

    # Process DataFrame
    df_wf = process_dataframe(df_wf)

    # Determine date range
    if args.date:
        try:
            start_date = datetime.strptime(args.date, '%Y-%m-%d')
            end_date = start_date + timedelta(days=args.days)
        except ValueError:
            logger.error("Invalid date format. Use YYYY-MM-DD")
            sys.exit(1)
    else:
        start_date = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = start_date + timedelta(days=args.days)

    # Generate output filename dynamically
    config.output_file = config.generate_output_filename(
        start_date=start_date,
        phase=args.phase,
        days=args.days,
        custom_output=args.output
    )

    # Filter by date range
    df_filtered = filter_by_date_range(df_wf, start_date, end_date)

    # Filter by workflow name if specified
    if args.workflow:
        try:
            pattern = re.compile(args.workflow)
            df_filtered = df_filtered[df_filtered['workflow'].apply(
                lambda x: bool(pattern.search(str(x))) if pd.notna(x) else False
            )]
            logger.info(f"Filtered by workflow pattern: '{args.workflow}', found {len(df_filtered)} workflows")
        except re.error as e:
            logger.error(f"Invalid regex pattern '{args.workflow}': {e}")
            sys.exit(1)

    if df_filtered.empty:
        logger.warning(f"No workflows found for the specified filters.")
        sys.exit(0)

    # Print summary statistics
    print_summary_stats(df_filtered)
    logger.warning(f"No workflows found for the specified date range.")
    # Create visualization
    create_timeline_chart(df_filtered, config.output_file)

    # Upload to S3 if configured
    if config.s3_bucket:
        upload_to_s3(config.output_file, config.s3_bucket, config.output_file, config)

    logger.info("Report generation complete!")


if __name__ == '__main__':
    main()
