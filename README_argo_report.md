# Argo Workflow Report Generator

A Python script to generate detailed reports and timeline visualizations of Argo workflows with optional S3 upload for static website hosting.

## Features

- ✅ **Secure Authentication**: Uses environment variables for bearer tokens (no hardcoded credentials)
- ✅ **Flexible Configuration**: Environment variables and command-line arguments
- ✅ **Comprehensive Logging**: Detailed logging for debugging and monitoring
- ✅ **Error Handling**: Robust error handling for API calls and data processing
- ✅ **Multiple Workflow Phases**: Support for Succeeded, Failed, Running, and Pending workflows
- ✅ **Date Range Filtering**: Filter workflows by specific dates or date ranges
- ✅ **Summary Statistics**: Display workflow duration statistics and top longest-running workflows
- ✅ **Interactive Timeline**: Generate interactive HTML timeline charts using Plotly
- ✅ **S3 Upload**: Automatically upload reports to S3 for static website hosting

## Installation

1. Install required dependencies:

```bash
pip install -r requirements.txt
```

## Configuration

### Environment Variables

You can configure the script using environment variables:

**Argo Configuration:**
- `ARGO_API_URL`: Argo API URL (default: `https://workflows.argocd.paidmedia.tda.link/api/v1/workflows/default`)
- `ARGO_BEARER_TOKEN`: Bearer token for authentication (recommended)
- `ARGO_NAMESPACE`: Kubernetes namespace (default: `default`)
- `ARGO_WORKFLOW_LIMIT`: Maximum number of workflows to fetch (default: `1000`)

**S3 Configuration (Optional):**
- `S3_BUCKET`: S3 bucket name for uploading reports (if not set, S3 upload is disabled)
- `S3_PREFIX`: Prefix path in S3 bucket (default: `argo-reports/`)
- `AWS_REGION`: AWS region (default: `eu-west-1`)
- `AWS_ACCESS_KEY_ID`: AWS access key (or use IAM role/AWS credentials file)
- `AWS_SECRET_ACCESS_KEY`: AWS secret key (or use IAM role/AWS credentials file)

Example `.env` file:

```bash
# Argo Configuration
export ARGO_BEARER_TOKEN="your-token-here"

# S3 Configuration
export S3_BUCKET="my-argo-reports-bucket"
export S3_PREFIX="argo-reports/"
export AWS_REGION="eu-west-1"
```

## Usage

### Basic Usage

Generate a report for today's succeeded workflows:

```bash
python argo_report.py
```

With Docker:

```bash
source .env
./dev.sh
```

### Specify a Date

Generate a report for a specific date:

```bash
./dev.sh --date 2025-01-15
```

### Filter by Workflow Phase

Generate a report for failed workflows:

```bash
./dev.sh --phase Failed
```

Available phases: `Succeeded`, `Failed`, `Running`, `Pending`

### Multi-Day Report

Generate a report spanning multiple days:

```bash
./dev.sh --date 2025-01-01 --days 7
```

### Filter by Workflow Name

Filter workflows by name using regex patterns:

```bash
# Exact workflow name
./dev.sh --workflow "my-workflow" --date 2025-10-15 --days 30

# Pattern matching (all workflows starting with "etl-")
./dev.sh --workflow "^etl-"

# Multiple patterns (workflows containing "data" or "sync")
./dev.sh --workflow "data|sync"

# Combine with other filters
./dev.sh --workflow "^daily-" 
```

### Custom Output File

Specify a custom output file:

```bash
./dev.sh --output ./reports/my_report.html
```

### Upload to S3

To enable S3 upload, simply set the `S3_BUCKET` environment variable:

```bash
export S3_BUCKET="my-argo-reports-bucket"
export S3_PREFIX="reports/"
./dev.sh
```

The script will automatically:
1. Generate the HTML report locally
2. Upload it to S3 with public-read ACL
3. Display the public URL for access

### Combined Example

```bash
S3_BUCKET="my-bucket" ./dev.sh \
  --date 2025-01-15 \
  --days 3 \
  --phase Succeeded
```

This will create `argo_wfs_2025_01_15_days_3.html` and upload it to `s3://my-bucket/argo-reports/argo_wfs_2025_01_15_days_3.html`

## S3 Static Website Hosting

### Setting Up S3 Bucket for Public Reports

1. **Create an S3 bucket:**
```bash
aws s3 mb s3://my-argo-reports-bucket --region eu-west-1
```

2. **Enable static website hosting:**
```bash
aws s3 website s3://my-argo-reports-bucket \
  --index-document argo_wfs_latest.html
```

3. **Configure bucket policy for public access:**

Create a file `bucket-policy.json`:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadGetObject",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::my-argo-reports-bucket/argo-reports/*"
    }
  ]
}
```

Apply the policy:
```bash
aws s3api put-bucket-policy \
  --bucket my-argo-reports-bucket \
  --policy file://bucket-policy.json
```

4. **Disable Block Public Access (if needed):**
```bash
aws s3api put-public-access-block \
  --bucket my-argo-reports-bucket \
  --public-access-block-configuration \
  "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"
```

5. **Access your reports:**
- Direct URL: `https://paidmedia-datalake-dbt-docs.s3.eu-central-1.amazonaws.com/argo-reports/argo_wfs_2025_11_04_full.html`
- Website URL: `https://paidmedia-datalake-dbt-docs.s3.eu-central-1.amazonaws.com/argo-reports/argo_wfs_2025_11_04_full.html`

### AWS Credentials

The Docker container uses your local AWS credentials. Make sure you have one of:

1. **AWS credentials file** (`~/.aws/credentials`):
```ini
[default]
aws_access_key_id = YOUR_ACCESS_KEY
aws_secret_access_key = YOUR_SECRET_KEY
```

2. **Environment variables**:
```bash
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
```

3. **IAM role** (when running on EC2/ECS)

## Output

The script generates:

1. **Console Output**: Summary statistics including:
   - Total workflows count
   - Unique workflow types
   - Duration statistics (average, median, min, max)
   - Top 5 longest-running workflows

2. **HTML Timeline Chart**: Interactive Plotly timeline showing:
   - Workflow execution timeline
   - Workflow names
   - Start and end times
   - Duration and status on hover

3. **S3 Upload** (if configured):
   - Uploads HTML to S3 with `text/html` content type
   - Sets `public-read` ACL for browser access
   - Displays S3 URI and public URL

## Dynamic Filename Generation

Files are automatically named based on parameters:

- `argo_wfs_2025_11_05_full.html` - Today's succeeded workflows
- `argo_wfs_2025_11_05_status_failed.html` - Failed workflows
- `argo_wfs_2025_01_01_days_7.html` - 7-day report
- `argo_wfs_2025_01_15_status_pending_days_3.html` - Complex example

## Security Best Practices

⚠️ **Important**: Never hardcode authentication tokens or AWS credentials in your scripts!

Always use environment variables or secure secret management:

```bash
# Set tokens in your shell profile or use a secure vault
export ARGO_BEARER_TOKEN="your-token-here"
export AWS_ACCESS_KEY_ID="your-aws-key"
export AWS_SECRET_ACCESS_KEY="your-aws-secret"

# Or use .env file (but never commit it to git!)
source .env
./dev.sh
```

## Example Output

```
2025-11-05 10:30:15 - INFO - Fetching workflows from https://workflows.argocd.paidmedia.tda.link/api/v1/workflows/default?listOptions.labelSelector=workflows.argoproj.io/phase=Succeeded&listOptions.limit=1000
2025-11-05 10:30:16 - INFO - Filtering workflows between 2025-11-05 00:00:00 and 2025-11-06 00:00:00
2025-11-05 10:30:16 - INFO - Found 45 workflows in date range

============================================================
WORKFLOW SUMMARY STATISTICS
============================================================
Total workflows: 45
Unique workflows: 12

Duration Statistics:
  Average: 234.56s
  Median: 180.23s
  Min: 45.12s
  Max: 890.45s

Top 5 longest running workflows:
           workflow                              run  duration_seconds
  data-pipeline-etl  data-pipeline-etl-a8c9d2f3e1b            890.45
  ml-training-job    ml-training-job-f9e8a7b6c5d4             567.89
  ...
============================================================

2025-11-05 10:30:17 - INFO - Creating timeline chart with 45 workflows
2025-11-05 10:30:18 - INFO - Timeline chart saved to argo_wfs_2025_11_05_full.html
2025-11-05 10:30:19 - INFO - File uploaded successfully!
2025-11-05 10:30:19 - INFO - S3 URI: s3://my-bucket/argo-reports/argo_wfs_2025_11_05_full.html
2025-11-05 10:30:19 - INFO - Public URL: https://my-bucket.s3.eu-west-1.amazonaws.com/argo-reports/argo_wfs_2025_11_05_full.html
2025-11-05 10:30:19 - INFO - Report generation complete!
```

## Automation with Cron

Schedule daily reports with automatic S3 upload:

```bash
# Add to crontab (crontab -e)
# Run daily at 8 AM
0 8 * * * cd /path/to/argo-report && source .env && ./dev.sh >> /var/log/argo-report.log 2>&1
```

## Troubleshooting

### No workflows found

- Check your date range
- Verify the workflow phase filter
- Ensure your bearer token has proper permissions

### Authentication errors

- Verify your bearer token is valid and not expired
- Check that the token has access to the specified namespace

### S3 Upload errors

- Verify AWS credentials are configured correctly
- Check that the S3 bucket exists and you have write permissions
- Ensure the bucket policy allows public read access (if needed)
- Verify the AWS region is correct

### Connection errors

- Verify the API URL is correct
- Check network connectivity to the Argo server
- Ensure any required VPN connections are active

## License

This script is provided as-is for internal use.
