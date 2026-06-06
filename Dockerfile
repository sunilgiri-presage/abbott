FROM python:3.9-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y bash
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential \
       libpq-dev \
       cron \
       gettext \
       dos2unix \
       netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app
COPY requirement.txt /usr/src/app/
RUN pip install --upgrade pip \
    && pip install -r requirement.txt

COPY . /usr/src/app/

RUN dos2unix /usr/src/app/entrypoint.sh \
    && chmod +x /usr/src/app/entrypoint.sh

RUN mkdir -p /tmp/numba_cache \
    && chmod 755 /tmp/numba_cache

RUN groupadd -r celery && useradd -r -g celery celery

RUN chown -R celery:celery /usr/src/app \
    && chown -R celery:celery /tmp/numba_cache

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/usr/src/app/entrypoint.sh"]
CMD ["gunicorn", "dashboard.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
