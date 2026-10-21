import { useState } from 'react';
import { useStrings } from '../lib/strings';
import { Lockup, SanadMark } from './Logo';

const Icon = {
  plus: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>,
  chat: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></svg>,
  kebab: <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.6" /><circle cx="12" cy="12" r="1.6" /><circle cx="12" cy="19" r="1.6" /></svg>,
  pen: <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" /></svg>,
  trash: <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /><path d="M9 6V4h6v2" /></svg>,
  collapse: <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="16" rx="3" /><line x1="9" y1="4" x2="9" y2="20" /></svg>,
};

/** Conversations rail: brand lockup, new conversation, history, and the connection card. */
export default function Sidebar({ chats, activeChatId, setActiveChatId, createNewChat, renameChat, deleteChat, collapsed, onToggle, footer }) {
  const { t } = useStrings();
  const [menu, setMenu] = useState(null);
  const [renaming, setRenaming] = useState(null);
  const [value, setValue] = useState('');

  const startRename = (chat) => { setRenaming(chat.id); setValue(chat.title); setMenu(null); };
  const finishRename = (id) => { if (value.trim()) renameChat(id, value.trim()); setRenaming(null); };
  const title = (chat) => (chat.title === 'New conversation' ? t('newConversationTitle') : chat.title);

  return (
    <aside className={`sn-rail sn-glass ${collapsed ? 'collapsed' : ''}`}>
      <div className="sn-rail-head">
        <Lockup compact={collapsed} />
        <button className="sn-icon-btn" onClick={onToggle} title={collapsed ? t('expand') : t('collapse')} aria-label={collapsed ? t('expand') : t('collapse')}>
          {Icon.collapse}
        </button>
      </div>

      <button className="sn-btn sn-btn-primary sn-newchat" onClick={createNewChat} title={t('newConversation')}>
        {Icon.plus}{!collapsed && <span>{t('newConversation')}</span>}
      </button>

      {!collapsed && (
        <>
          <div className="sn-rail-section">{t('conversations')}</div>
          <div className="sn-chatlist">
            {chats.length === 0 && <div className="sn-empty">{t('noConversations')}</div>}
            {chats.map(chat => {
              const active = chat.id === activeChatId;
              const open = menu === chat.id;
              if (renaming === chat.id) {
                return (
                  <div key={chat.id} className="px-1 py-0.5">
                    <input className="sn-rename" value={value} onChange={e => setValue(e.target.value)}
                      onBlur={() => finishRename(chat.id)} onKeyDown={e => { if (e.key === 'Enter') finishRename(chat.id); if (e.key === 'Escape') setRenaming(null); }} autoFocus />
                  </div>
                );
              }
              return (
                <div key={chat.id} className="sn-chat-row">
                  <button className={`sn-chat-item ${active ? 'active' : ''}`} onClick={() => setActiveChatId(chat.id)} title={title(chat)}>
                    <span className="glyph">{Icon.chat}</span>
                    <span className="label">{title(chat)}</span>
                  </button>
                  <button className={`sn-chat-kebab ${open ? 'open' : ''}`} onClick={e => { e.stopPropagation(); setMenu(open ? null : chat.id); }} aria-label="More">
                    {Icon.kebab}
                  </button>
                  {open && (
                    <>
                      <div className="fixed inset-0 z-40" onClick={() => setMenu(null)} />
                      <div className="sn-menu">
                        <button onClick={() => startRename(chat)}>{Icon.pen}{t('rename')}</button>
                        <button className="danger" onClick={() => { deleteChat(chat.id); setMenu(null); }}>{Icon.trash}{t('delete')}</button>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </>
      )}
      {collapsed && <div className="flex-1" />}

      <div className="sn-rail-foot">
        {collapsed ? <div className="sn-mark-tile" style={{ width: 34, height: 34 }}><SanadMark size={18} /></div> : footer}
        {!collapsed && <div className="sn-foot-note">{t('poweredBy')}</div>}
      </div>
    </aside>
  );
}
