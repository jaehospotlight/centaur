FROM oven/bun:1.3.13-slim

WORKDIR /repo
ENV NODE_ENV=production

RUN bun install -g pnpm@10.28.1

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY services/slackbot/package.json services/slackbot/package.json
COPY packages/api-client/package.json packages/api-client/package.json
RUN pnpm install --filter slackbot... --prod --frozen-lockfile

COPY packages/api-client/ packages/api-client/
COPY services/slackbot/ services/slackbot/
WORKDIR /repo/services/slackbot

EXPOSE 3001
ENV PORT=3001
CMD ["bun", "src/index.ts"]
