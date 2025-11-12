#!/usr/bin/env bash

set -e # exit on first error

CURRENT_DIR="$( cd "$( dirname "$0" )" && pwd )"
pushd $CURRENT_DIR 1>/dev/null
DIR="/argo-report"

IMAGE_TAG="argo-report-to-s3"

echo "Building image '$IMAGE_TAG'..."
#pipenv lock --requirements > requirements.txt
docker build -t "$IMAGE_TAG" . 1>/dev/null
docker run --rm -it \
  -v "$CURRENT_DIR:$DIR" \
  -v ~/.aws:/root/.aws \
  -e ARGO_BEARER_TOKEN="${ARGO_BEARER_TOKEN}" \
  -e ARGO_API_URL="${ARGO_API_URL}" \
  -e S3_BUCKET="${S3_BUCKET}" \
  -w "$DIR" \
  $IMAGE_TAG \
  python argo_report.py "$@"
popd 1>/dev/null


  #-e ARGO_NAMESPACE="${ARGO_NAMESPACE}" \
  #-e ARGO_WORKFLOW_LIMIT="${ARGO_WORKFLOW_LIMIT}" \
  #-e S3_PREFIX="${S3_PREFIX}" \
  #-e AWS_REGION="${AWS_REGION}" \
  #-e AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID}" \
  #-e AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY}" \
  #-e AWS_SESSION_TOKEN="${AWS_SESSION_TOKEN}" \