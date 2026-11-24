#!/bin/sh
set -eu

export NPM_CONFIG_REGISTRY='https://registry.npmjs.org/'
npm install --omit=dev --no-audit --no-fund --registry='https://registry.npmjs.org/'

mkdir -p dist
cp server.js queries.js demo.js phonearea.js phone.dat package.json run.sh dist/
cp -R public dist/public
cp -R node_modules dist/node_modules
chmod 755 dist/run.sh
