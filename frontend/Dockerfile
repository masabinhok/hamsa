# The checker desk and public pages. Build from the repo root: docker compose build
FROM node:22-slim
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# The browser calls the API directly, so its address is baked into the build.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
# Link previews in Telegram and Messenger fetch the preview image from this address.
ARG SITE_URL=http://localhost:3000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL SITE_URL=$SITE_URL NEXT_TELEMETRY_DISABLED=1
RUN npm run build
EXPOSE 3000
CMD ["npm", "start"]
