FROM python:3.12 as stage1

ENV PYTHONUNBUFFERED 1

RUN python -m pip install hatch

FROM stage1 as stage2
RUN mkdir /app
WORKDIR /app

COPY pyproject.toml /app
COPY config/ /app/config/
COPY README.md /app

COPY . .

FROM stage2 as stage3
CMD ["hatch", "run", "prod:run"]
