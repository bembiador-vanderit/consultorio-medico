export const notificationsChangedEvent = "atlas:notifications-changed";

export function announceNotificationsChanged() {
  window.dispatchEvent(new Event(notificationsChangedEvent));
}
