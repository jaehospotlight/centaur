"use client";

import dynamic from "next/dynamic";
import rehypeHighlight from "rehype-highlight";
import remarkGfm from "remark-gfm";

const ReactMarkdown = dynamic(() => import("react-markdown").then((m) => m.default), {
  ssr: false,
  loading: () => null,
});

export function MarkdownView({ text }: { text: string }) {
  return (
    <div className="prose-console text-zinc-300">
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeHighlight]}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
