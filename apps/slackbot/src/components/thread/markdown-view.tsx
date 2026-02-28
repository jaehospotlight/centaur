"use client";

import dynamic from "next/dynamic";
import remarkGfm from "remark-gfm";
import rehypePrettyCode from "rehype-pretty-code";

const ReactMarkdown = dynamic(() => import("react-markdown").then((m) => m.default), {
  ssr: false,
  loading: () => null,
});

const prettyCodeOptions = {
  theme: "github-dark",
  keepBackground: false,
  defaultLang: "txt",
};

export function MarkdownView({ text }: { text: string }) {
  return (
    <div className="prose-console">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[[rehypePrettyCode, prettyCodeOptions]]}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
