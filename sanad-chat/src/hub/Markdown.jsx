import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const components = {
  p: ({ node, ...props }) => <p className="my-1 leading-[1.7]" {...props} />,
  strong: ({ node, ...props }) => <strong style={{ color: 'var(--brand-lo)', fontWeight: 800 }} {...props} />,
  em: ({ node, ...props }) => <em style={{ color: 'var(--text-dim)' }} {...props} />,
  ul: ({ node, ...props }) => <ul className="my-1.5 space-y-0.5 ps-5 list-disc" {...props} />,
  ol: ({ node, ...props }) => <ol className="my-1.5 space-y-0.5 ps-5 list-decimal" {...props} />,
  li: ({ node, ...props }) => <li className="leading-[1.65]" {...props} />,
  h1: ({ node, ...props }) => <h3 className="text-[14px] font-bold my-2" style={{ color: 'var(--brand-lo)' }} {...props} />,
  h2: ({ node, ...props }) => <h3 className="text-[14px] font-bold my-2" style={{ color: 'var(--brand-lo)' }} {...props} />,
  h3: ({ node, ...props }) => <h3 className="text-[13.5px] font-bold my-1.5" style={{ color: 'var(--brand-lo)' }} {...props} />,
  a: ({ node, ...props }) => <a target="_blank" rel="noreferrer noopener" style={{ color: 'var(--brand)', textDecoration: 'underline' }} {...props} />,
  table: ({ node, ...props }) => (
    <div className="my-2 overflow-x-auto"><table className="hub-table" {...props} /></div>
  ),
  code: ({ node, className, children, ...props }) => {
    const text = String(children ?? '');
    const block = /language-/.test(className || '') || text.includes('\n');
    return block
      ? <code className="block p-2 rounded my-1 text-[12px] overflow-x-auto" style={{ background: 'var(--code-bg)' }} {...props}>{children}</code>
      : <code className="px-1 py-0.5 rounded text-[12px]" style={{ background: 'rgba(47,111,168,0.10)', color: 'var(--brand-lo)' }} {...props}>{children}</code>;
  },
  pre: ({ node, ...props }) => <pre className="my-1" {...props} />,
  blockquote: ({ node, ...props }) => <blockquote className="ps-3 my-2" style={{ borderInlineStart: '3px solid var(--brand)', color: 'var(--text-md)' }} {...props} />,
};

export default function Markdown({ children }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{children || ''}</ReactMarkdown>;
}
