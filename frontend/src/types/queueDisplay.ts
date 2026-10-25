export type QueueDisplayLine = {
  queue_line_id: number;
  destination: string;
  sort_order: number;
  is_active: boolean;
  line_name?: string;
};

export type QueueDisplay = {
  id: number;
  center_id: number;
  center_name: string;
  waiting_room_id?: number | null;
  waiting_room_name?: string | null;
  name: string;
  is_active: boolean;
  show_service_name: boolean;
  show_provider_name: boolean;
  recent_call_limit: number;
  audio_enabled: boolean;
  audio_volume: number;
  audio_language: "es-DO" | "es";
  audio_voice_uri: string | null;
  audio_rate: number;
  audio_pitch: number;
  repeat_count: number;
  repeat_delay_ms: number;
  announce_service_name: boolean;
  announce_provider_name: boolean;
  lines: QueueDisplayLine[];
};

export type QueueDisplayToken = QueueDisplay & { access_token: string };

export type PublicCall = {
  ticket_code: string;
  destination: string;
  called_at: string;
  call_revision: number;
  queue_line_name: string | null;
  provider_name: string | null;
};

export type PublicQueueDisplayState = {
  display_name: string;
  center_name: string;
  waiting_room_name?: string | null;
  provider_names?: string[];
  service_names?: string[];
  current_calls: PublicCall[];
  recent_calls: PublicCall[];
  updated_at: string;
  audio: Pick<QueueDisplay, "audio_enabled" | "audio_volume" | "audio_language" | "audio_voice_uri" | "audio_rate" | "audio_pitch" | "repeat_count" | "repeat_delay_ms" | "announce_service_name" | "announce_provider_name">;
};
