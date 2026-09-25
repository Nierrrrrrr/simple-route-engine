FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
COPY requirements.lock /opt/route/requirements.lock
RUN pip install --no-cache-dir --no-deps -r /opt/route/requirements.lock && pip check
COPY entrypoint.py /opt/route/entrypoint.py
COPY playbooks /opt/route/playbooks
ENV HOME=/tmp/route-home ANSIBLE_HOME=/tmp/route-home/.ansible ANSIBLE_LOCAL_TEMP=/tmp/route-home/.ansible/tmp PYTHONDONTWRITEBYTECODE=1
RUN mkdir -p /artifacts && chown 1000:1000 /artifacts
USER 1000:1000
ENTRYPOINT ["python","/opt/route/entrypoint.py"]
