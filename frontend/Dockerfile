FROM node:24-bookworm-slim

WORKDIR /app/frontend
RUN chown node:node /app/frontend
# Usuario node (uid 1000): lo que se genere en el volumen (schema.d.ts, package-lock.json)
# queda a tu nombre y no de root.
USER node

COPY --chown=node:node package.json package-lock.json ./
RUN npm ci --no-audit --no-fund && cp package-lock.json node_modules/.sta-lock

COPY --chown=node:node . .

ENTRYPOINT ["./docker-entrypoint.sh"]
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
