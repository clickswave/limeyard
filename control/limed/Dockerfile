# limeyard control plane. Drives each target as its own isolated `docker compose`
# project via the host Docker socket, and serves the HTTP API the UI talks to.
# Dev use only.
FROM docker:27-cli

RUN apk add --no-cache python3 py3-yaml docker-cli-compose git ca-certificates curl

COPY lime.py api.py scorer.py pin.py /opt/limed/
RUN chmod +x /opt/limed/lime.py && ln -s /opt/limed/lime.py /usr/local/bin/lime

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/opt/limed
WORKDIR /work
ENTRYPOINT ["lime"]
CMD ["monitor"]
