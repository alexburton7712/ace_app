import type { Turn } from "./types";

function turnText(turn: Turn): string { return turn.text ?? turn.content ?? ""; }
function isUser(turn: Turn): boolean { return turn.role === "user" || turn.speaker?.toLowerCase() === "user"; }

function message(turn: Turn): HTMLElement {
  const article = document.createElement("article");
  article.className = `message ${isUser(turn) ? "message-user" : "message-ace"}`;
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const speaker = document.createElement("span");
  speaker.textContent = isUser(turn) ? "You" : "Ace";
  meta.append(speaker);
  const rawTime = turn.timestamp ?? turn.created_at;
  if (rawTime) {
    const time = document.createElement("time");
    const date = new Date(rawTime);
    time.dateTime = rawTime;
    time.textContent = Number.isNaN(date.getTime()) ? "" : date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    meta.append(time);
  }
  const body = document.createElement("p");
  body.textContent = turnText(turn); // Agent responses are never interpreted as markup.
  article.append(meta, body);
  return article;
}

function expand(turn: Turn): Turn[] {
  if (turn.user_text === undefined && turn.assistant_text === undefined) return [turn];
  const timestamp = turn.timestamp ?? turn.created_at;
  const messages: Turn[] = [];
  if (turn.user_text) messages.push({ role: "user", text: turn.user_text, timestamp });
  if (turn.assistant_text) messages.push({ role: "assistant", text: turn.assistant_text, timestamp });
  return messages;
}

export function renderConversation(container: HTMLElement, turns: Turn[], contextCount: number): void {
  container.replaceChildren();
  if (!turns.length) {
    const empty = document.createElement("div");
    empty.className = "conversation-empty";
    const title = document.createElement("p");
    title.textContent = "Start with your voice";
    const copy = document.createElement("span");
    copy.textContent = "Your conversation will appear here.";
    empty.append(title, copy);
    container.append(empty);
    return;
  }
  const split = Math.max(0, turns.length - Math.max(0, contextCount));
  const groups: Array<[string, Turn[]]> = [];
  if (split) groups.push(["Earlier", turns.slice(0, split)]);
  groups.push([`Newest ${Math.min(contextCount, turns.length)} turns · assumed in context`, turns.slice(split)]);
  groups.forEach(([label, entries]) => {
    const section = document.createElement("section");
    const heading = document.createElement("h3");
    heading.className = "transcript-group";
    heading.textContent = label;
    section.append(heading, ...entries.flatMap(expand).map(message));
    container.append(section);
  });
  container.scrollTop = container.scrollHeight;
}
