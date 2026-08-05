FROM node:22-alpine

WORKDIR /app

ENV PATH=/app/node_modules/.bin:$PATH

# Dependencias primero (mejor cache de capas de Docker).
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then \
      npm ci --prefer-offline; \
    else \
      npm install; \
    fi

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]