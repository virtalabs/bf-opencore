FROM python:3.12-slim

RUN pip install --no-cache-dir scapy==2.5.0

COPY generate.py /generate.py

CMD ["python3", "-u", "/generate.py"]
