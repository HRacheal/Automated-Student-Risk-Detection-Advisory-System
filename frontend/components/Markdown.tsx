import { Fragment, type ReactNode } from "react";

/** Minimal, safe renderer for the chatbot's markdown (**bold**, _italic_, bullets, headings). No raw HTML. */
function inline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|_[^_]+_)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i} className="font-semibold text-slate-900">{p.slice(2, -2)}</strong>;
    if (p.length > 2 && p.startsWith("_") && p.endsWith("_")) return <em key={i} className="text-slate-600">{p.slice(1, -1)}</em>;
    return <Fragment key={i}>{p}</Fragment>;
  });
}

export default function Markdown({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1 text-sm leading-relaxed text-slate-700">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-1.5" />;
        const bullet = line.match(/^(\s*)[-*] (.*)$/);
        if (bullet) {
          const nested = bullet[1].length >= 2;
          return (
            <div key={i} className={`flex gap-2 ${nested ? "pl-6 text-slate-600" : "pl-1"}`}>
              <span className="select-none text-slate-400">{nested ? "◦" : "•"}</span>
              <span>{inline(bullet[2])}</span>
            </div>
          );
        }
        const heading = line.match(/^#{1,4} (.*)$/);
        if (heading) return <p key={i} className="pt-1 font-semibold text-slate-900">{inline(heading[1])}</p>;
        return <p key={i}>{inline(line)}</p>;
      })}
    </div>
  );
}
