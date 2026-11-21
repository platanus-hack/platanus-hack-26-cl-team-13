FROM python:3.12-alpine
COPY proxy.py /app/proxy.py
USER nobody
EXPOSE 3128 3129
CMD ["python", "-u", "/app/proxy.py"]
