FROM node:22-bookworm

RUN npm install -g npm@11.5

RUN mkdir /code && chown node:node /code
WORKDIR /code

# run as the node user so installed files are owned correctly
USER node

# install deps before copying source — keeps this layer cached across code changes
COPY package.json package.json
RUN npm install

COPY . /code/
