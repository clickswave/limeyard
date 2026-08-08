# vuln_apps_manager: a thin control plane that drives each vuln app as its own
# isolated `docker compose` project via the host Docker socket. Dev use only.
FROM docker:27-cli

RUN apk add --no-cache python3 py3-yaml docker-cli-compose git ca-certificates curl

COPY vam.py /usr/local/bin/vam
RUN chmod +x /usr/local/bin/vam

ENV PYTHONUNBUFFERED=1
WORKDIR /work
ENTRYPOINT ["vam"]
CMD ["monitor"]
