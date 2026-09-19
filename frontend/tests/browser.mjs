import { JSDOM } from "jsdom";

export function createBrowser() {
  const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: "http://localhost:5173" });
  Object.assign(globalThis, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, Event: dom.window.Event, IS_REACT_ACT_ENVIRONMENT: true });
  const changes = new Set();
  let desktop = true;
  window.matchMedia = (media) => ({ media, get matches() { return desktop; }, addEventListener: (_, listener) => changes.add(listener), removeEventListener: (_, listener) => changes.delete(listener) });
  // jsdom has no native dialog top layer; browser QA verifies focus/inert behavior.
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  dom.window.HTMLDialogElement.prototype.close = function () { this.open = false; };
  return { dom, setDesktop(value) { desktop = value; changes.forEach((listener) => listener()); } };
}
