FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy vite config
COPY vite.config.js ./
COPY postcss.config.js ./
COPY tailwind.config.js ./

# Expose Vite dev server port
EXPOSE 3000

# Start Vite dev server with host binding
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "3000"]