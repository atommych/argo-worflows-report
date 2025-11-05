FROM python:3.8-slim

COPY *.txt ./

RUN pip install -r ./requirements.txt

COPY *.py ./