# Seraphine Auto-Fixer. No dependencies: Bun runs the TypeScript directly.
FROM oven/bun:1.1.38-alpine
WORKDIR /app
COPY package.json tsconfig.json ./
COPY src ./src
USER bun
EXPOSE 3000
CMD ["bun", "src/main.ts"]
