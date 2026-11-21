"use client";

import { FormEvent, useEffect, useState } from "react";
import { PageTitle } from "@/components/Shell";
import { apiJson, isSystemAdmin, type User } from "@/lib/api";

type TelegramChat = { id: string; title: string; type: string; selected: boolean };
type PendingTrade = {
  id: string;
  chat_title: string;
  symbol: string;
  side: string;
  entry: string;
  stop_loss: string | null;
  take_profit: string | null;
  volume: string;
  expires_at: string | null;
};

export default function TelegramPage() {
  const [me, setMe] = useState<User | null>(null);
  const [message, setMessage] = useState("");
  const [appId, setAppId] = useState("");
  const [telegramReady, setTelegramReady] = useState(false);
  const [accountConnected, setAccountConnected] = useState(false);
  const [codeSent, setCodeSent] = useState(false);
  const [chats, setChats] = useState<TelegramChat[]>([]);
  const [chatsLoaded, setChatsLoaded] = useState(false);
  const [autoExecute, setAutoExecute] = useState(false);
  const [signals, setSignals] = useState<PendingTrade[]>([]);

  function loadStatus() {
    apiJson<{ app_id: string; bot_token_set: boolean; account_connected: boolean; auto_execute: boolean }>("/api/v1/telegram")
      .then((body) => {
        setAppId(body.app_id || "");
        setTelegramReady(Boolean(body.bot_token_set));
        setAccountConnected(Boolean(body.account_connected));
        setAutoExecute(Boolean(body.auto_execute));
      })
      .catch(() => undefined);
  }

  useEffect(() => {
    apiJson<User>("/api/v1/auth/me").then(setMe).catch(() => undefined);
    loadStatus();
  }, []);

  useEffect(() => {
    let stopped = false;
    let timer = 0;
    const load = async () => {
      try {
        const body = await apiJson<{ auto_execute: boolean; signals: PendingTrade[] }>("/api/v1/telegram/signals");
        if (stopped) return;
        setAutoExecute(Boolean(body.auto_execute));
        setSignals(body.signals || []);
      } catch {
        /* keep the last list when the desk is briefly unreachable */
      } finally {
        if (!stopped) timer = window.setTimeout(load, 5000);
      }
    };
    load();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (!accountConnected) {
      setChats([]);
      setChatsLoaded(false);
      return;
    }
    let cancelled = false;
    setChatsLoaded(false);
    apiJson<{ chats: TelegramChat[] }>("/api/v1/telegram/chats")
      .then((body) => {
        if (cancelled) return;
        setChats(body.chats || []);
        setChatsLoaded(true);
      })
      .catch((err) => {
        if (cancelled) return;
        const text = err instanceof Error ? err.message : "Telegram chats were not loaded";
        setChatsLoaded(true);
        if (text.startsWith("Sign in to Telegram")) setAccountConnected(false);
        setMessage(text);
      });
    return () => {
      cancelled = true;
    };
  }, [accountConnected]);

  async function saveTelegram(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const body = await apiJson<{ app_id: string; bot_token_set: boolean }>("/api/v1/telegram", {
        method: "PUT",
        body: JSON.stringify({
          app_id: form.get("app_id"),
          api_hash: form.get("api_hash"),
          bot_token: form.get("bot_token"),
        }),
      });
      setAppId(body.app_id || "");
      setTelegramReady(Boolean(body.bot_token_set));
      setMessage("Telegram saved.");
      loadStatus();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Telegram was not saved");
    }
  }

  async function sendTelegramTest() {
    const form = document.getElementById("telegram-settings") as HTMLFormElement | null;
    const token = form ? String(new FormData(form).get("bot_token") || "") : "";
    try {
      const body = await apiJson<{ sent: boolean; bot: string }>("/api/v1/telegram/test", {
        method: "POST",
        body: JSON.stringify({ bot_token: token }),
      });
      setMessage(body.bot ? `Test sent from @${body.bot}. Check Telegram.` : "Test sent. Check Telegram.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Telegram test was not sent");
    }
  }

  async function sendLoginCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const phone = String(new FormData(event.currentTarget).get("phone") || "");
    try {
      const body = await apiJson<{ sent: boolean; connected: boolean }>("/api/v1/telegram/user/code", {
        method: "POST",
        body: JSON.stringify({ phone }),
      });
      if (body.connected) {
        setAccountConnected(true);
        setCodeSent(false);
        setMessage("Telegram account connected.");
        return;
      }
      setCodeSent(true);
      setMessage("Telegram sent a login code. Enter it here.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Telegram did not send a code");
    }
  }

  async function confirmLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      await apiJson("/api/v1/telegram/user/confirm", {
        method: "POST",
        body: JSON.stringify({ code: form.get("code"), password: form.get("password") || "" }),
      });
      setCodeSent(false);
      setAccountConnected(true);
      setMessage("Telegram account connected.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Telegram did not accept that code");
    }
  }

  async function saveChats(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const body = await apiJson<{ chats: TelegramChat[] }>("/api/v1/telegram/chats", {
        method: "PUT",
        body: JSON.stringify({ chat_ids: chats.filter((chat) => chat.selected).map((chat) => chat.id) }),
      });
      const saved = new Set((body.chats || []).map((chat) => chat.id));
      setChats((current) => current.map((chat) => ({ ...chat, selected: saved.has(chat.id) })));
      setMessage("Signal chats saved. New messages in the checked chats go to DeepSeek.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Signal chats were not saved");
    }
  }

  async function toggleAutoExecute(enabled: boolean) {
    try {
      const body = await apiJson<{ auto_execute: boolean }>("/api/v1/telegram/auto-execute", {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      });
      setAutoExecute(body.auto_execute);
      setMessage(body.auto_execute ? "Auto execute is on. A found signal is sent immediately." : "Auto execute is off. Found signals stay pending for 10 minutes.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Auto execute was not changed");
    }
  }

  async function executeSignal(id: string) {
    try {
      const body = await apiJson<{ message: string }>(`/api/v1/telegram/signals/${id}/execute`, { method: "POST" });
      setSignals((current) => current.filter((row) => row.id !== id));
      setMessage(body.message);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "That signal was not executed");
    }
  }

  async function disconnectTelegram() {
    try {
      await apiJson("/api/v1/telegram/user", { method: "DELETE" });
      setAccountConnected(false);
      setCodeSent(false);
      setChats([]);
      setMessage("Telegram account disconnected.");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Telegram account was not disconnected");
    }
  }

  return (
    <div className="telegram-layout">
      <div className="flex flex-col gap-8 min-w-0">
      {isSystemAdmin(me?.roles) ? (
      <section>
        <PageTitle title="Telegram" detail="App and bot keys are saved in Settings. This page is for the phone login and signal chats." />
        <form id="telegram-settings" className="flex flex-col gap-3" autoComplete="off" onSubmit={saveTelegram}>
          <label className="flex flex-col gap-1 text-sm">
            App ID
            <input name="app_id" value={appId} onChange={(event) => setAppId(event.target.value)} autoComplete="off" required />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            App API hash
            <input name="api_hash" type="password" autoComplete="off" placeholder={telegramReady ? "Leave blank to keep the saved hash" : ""} required={!telegramReady} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Bot token
            <input name="bot_token" type="password" autoComplete="off" placeholder={telegramReady ? "Leave blank to keep the saved token" : "From BotFather"} required={!telegramReady} />
          </label>
          <div className="flex gap-2">
            <button className="primary" type="submit">Save</button>
            <button className="ghost" type="button" onClick={sendTelegramTest}>Send test</button>
          </div>
        </form>
        <p className="text-sm text-muted mt-3">Prefer Settings for these keys. Users only sign in with their phone below.</p>
      </section>
      ) : (
        <section>
          <PageTitle title="Telegram" detail="Sign in with your phone. The app and bot keys are set in Settings." />
          {telegramReady ? null : <p className="text-sm text-muted">Telegram is not ready yet. The app still needs to be saved in Settings.</p>}
        </section>
      )}
      <section>
        <h2 className="text-lg font-semibold">Your notifications</h2>
        <p className="text-sm text-muted mt-1">These credentials belong to this login. Mining income, contract updates, and account updates are sent to the chat id.</p>
        <NoticeForm />
      </section>
      <section>
        <h2 className="text-lg font-semibold">Copy signals</h2>
        <p className="text-sm text-muted mt-1">Sign in with your phone so the desk can read chats you already belong to. DeepSeek keeps a message only when it has a pair, a direction, and an entry. Stop and target may be missing. Ordinary chat is ignored. A found trade stays pending for 10 minutes, then it is deleted if it was not executed. Turn on auto execute to send it as soon as it is found. The risk engine still decides. The reply arrives on the bot chat. The chat name is stored as the trade comment.</p>
        <label className="text-sm flex gap-2 items-center mt-4">
          <input className="w-auto" type="checkbox" checked={autoExecute} onChange={(event) => toggleAutoExecute(event.target.checked)} />
          Auto execute found signals
        </label>
        {accountConnected ? (
          <form className="flex flex-col gap-3 mt-4" onSubmit={saveChats}>
            <ul className="border border-line rounded bg-panel max-h-64 overflow-auto">
              {chats.length ? chats.map((chat) => (
                <li key={chat.id} className="flex items-center gap-3 px-3 py-2 border-b border-line last:border-b-0">
                  <input
                    className="w-auto"
                    type="checkbox"
                    checked={chat.selected}
                    onChange={(event) => setChats((current) => current.map((row) => row.id === chat.id ? { ...row, selected: event.target.checked } : row))}
                  />
                  <span className="flex-1">{chat.title}</span>
                  <span className="text-sm text-muted">{chat.type}</span>
                </li>
              )) : <li className="px-3 py-2 text-sm text-muted">{chatsLoaded ? "No chats to show." : "Loading chats."}</li>}
            </ul>
            <div className="flex gap-2">
              <button className="primary" type="submit">Save chats</button>
              <button className="ghost" type="button" onClick={disconnectTelegram}>Disconnect</button>
            </div>
          </form>
        ) : (
          <div className="flex flex-col gap-4 mt-4">
            <form className="flex flex-col gap-3" autoComplete="off" onSubmit={sendLoginCode}>
              <label className="flex flex-col gap-1 text-sm">
                Phone
                <input name="phone" autoComplete="off" placeholder="+15551234567" required />
              </label>
              <button className="primary w-fit" type="submit">Send code</button>
            </form>
            {codeSent ? (
              <form className="flex flex-col gap-3" autoComplete="off" onSubmit={confirmLogin}>
                <label className="flex flex-col gap-1 text-sm">
                  Login code
                  <input name="code" autoComplete="one-time-code" inputMode="numeric" required />
                </label>
                <label className="flex flex-col gap-1 text-sm">
                  Cloud password
                  <input name="password" type="password" autoComplete="off" placeholder="Only if Telegram asks for it" />
                </label>
                <button className="primary w-fit" type="submit">Confirm</button>
              </form>
            ) : null}
          </div>
        )}
      </section>
      {message ? <p className="text-sm">{message}</p> : null}
      </div>
      <aside className="telegram-pending">
        <h2>Pending signals</h2>
        <p className="text-sm text-muted mb-3">A found trade stays here for 10 minutes.</p>
        <ul className="border border-line rounded bg-panel">
          {signals.length ? signals.map((signal) => (
            <li key={signal.id} className="flex flex-col gap-2 px-3 py-3 border-b border-line last:border-b-0">
              <span>
                {signal.side} {signal.symbol} at {signal.entry} · lot {signal.volume}
                {signal.stop_loss ? ` · stop ${signal.stop_loss}` : ""}
                {signal.take_profit ? ` · target ${signal.take_profit}` : ""}
                <span className="block text-sm text-muted">{signal.chat_title} · until {signal.expires_at ? new Date(signal.expires_at).toLocaleTimeString() : "10 minutes"}</span>
              </span>
              <button className="ghost w-fit" type="button" onClick={() => executeSignal(signal.id)}>Execute</button>
            </li>
          )) : <li className="px-3 py-2 text-sm text-muted">No pending signals.</li>}
        </ul>
      </aside>
    </div>
  );
}

function NoticeForm() {
  const [appId, setAppId] = useState("");
  const [chatId, setChatId] = useState("");
  const [hashSet, setHashSet] = useState(false);
  const [tokenSet, setTokenSet] = useState(false);
  const [connected, setConnected] = useState(false);
  const [note, setNote] = useState("");

  useEffect(() => {
    apiJson<{ connected: boolean; app_id: string; chat_id: string; api_hash_set: boolean; bot_token_set: boolean }>("/api/v1/telegram/notify")
      .then((body) => {
        setAppId(body.app_id || "");
        setChatId(body.chat_id || "");
        setHashSet(Boolean(body.api_hash_set));
        setTokenSet(Boolean(body.bot_token_set));
        setConnected(Boolean(body.connected));
      })
      .catch((err: Error) => setNote(err.message));
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const body = await apiJson<{ connected: boolean }>("/api/v1/telegram/notify", {
        method: "PUT",
        body: JSON.stringify({
          app_id: appId,
          api_hash: String(form.get("api_hash") || ""),
          bot_token: String(form.get("bot_token") || ""),
          chat_id: chatId,
        }),
      });
      setConnected(Boolean(body.connected));
      setHashSet(true);
      setTokenSet(true);
      setNote("Telegram connected for this login.");
    } catch (err) {
      setNote(err instanceof Error ? err.message : "Telegram was not saved");
    }
  }

  return (
    <form className="flex flex-col gap-3 mt-3 max-w-md" autoComplete="off" onSubmit={onSubmit}>
      <p className="text-sm">{connected ? "Connected" : "Not connected"}</p>
      <input value={appId} onChange={(event) => setAppId(event.target.value)} inputMode="numeric" placeholder="App ID from my.telegram.org" required />
      <input name="api_hash" type="password" autoComplete="off" placeholder={hashSet ? "API hash saved. Leave blank to keep it" : "API hash from my.telegram.org"} required={!hashSet} />
      <input name="bot_token" type="password" autoComplete="off" placeholder={tokenSet ? "Bot token saved. Leave blank to keep it" : "Bot token from BotFather"} required={!tokenSet} />
      <input value={chatId} onChange={(event) => setChatId(event.target.value)} inputMode="numeric" placeholder="Chat ID" required />
      <div className="flex gap-2">
        <button className="primary" type="submit">Save and connect</button>
        <button className="ghost" type="button" onClick={() => apiJson("/api/v1/telegram/notify/test", { method: "POST" }).then(() => setNote("Test sent. Check Telegram.")).catch((err: Error) => setNote(err.message))}>Send a test</button>
      </div>
      {note ? <p className="text-sm">{note}</p> : null}
    </form>
  );
}
