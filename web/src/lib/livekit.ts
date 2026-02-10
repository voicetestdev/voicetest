/**
 * LiveKit client wrapper for browser-based voice calls.
 */

import {
  Room,
  RoomEvent,
  Track,
  RemoteParticipant,
  RemoteTrackPublication,
  ConnectionState,
  type AudioTrack,
} from "livekit-client";

export interface LiveKitConnection {
  room: Room;
  disconnect: () => Promise<void>;
  setMuted: (muted: boolean) => Promise<void>;
  isMuted: () => boolean;
}

export interface LiveKitCallbacks {
  onConnected?: () => void;
  onDisconnected?: () => void;
  onError?: (error: Error) => void;
  onAudioTrackSubscribed?: (track: AudioTrack, participant: RemoteParticipant) => void;
  onAudioTrackUnsubscribed?: (track: AudioTrack, participant: RemoteParticipant) => void;
  onConnectionStateChanged?: (state: ConnectionState) => void;
}

export async function connectToRoom(
  url: string,
  token: string,
  callbacks: LiveKitCallbacks = {}
): Promise<LiveKitConnection> {
  const room = new Room({
    adaptiveStream: true,
    dynacast: true,
    audioCaptureDefaults: {
      autoGainControl: true,
      echoCancellation: true,
      noiseSuppression: true,
    },
  });

  room.on(RoomEvent.Connected, () => {
    callbacks.onConnected?.();
  });

  room.on(RoomEvent.Disconnected, () => {
    callbacks.onDisconnected?.();
  });

  room.on(RoomEvent.ConnectionStateChanged, (state: ConnectionState) => {
    callbacks.onConnectionStateChanged?.(state);
  });

  room.on(
    RoomEvent.TrackSubscribed,
    (track: Track, _publication: RemoteTrackPublication, participant: RemoteParticipant) => {
      if (track.kind === Track.Kind.Audio) {
        callbacks.onAudioTrackSubscribed?.(track as AudioTrack, participant);

        const audioElement = track.attach();
        audioElement.id = `audio-${participant.identity}`;
        document.body.appendChild(audioElement);
      }
    }
  );

  room.on(
    RoomEvent.TrackUnsubscribed,
    (track: Track, _publication: RemoteTrackPublication, participant: RemoteParticipant) => {
      if (track.kind === Track.Kind.Audio) {
        callbacks.onAudioTrackUnsubscribed?.(track as AudioTrack, participant);

        track.detach().forEach((el: HTMLMediaElement) => el.remove());
      }
    }
  );

  try {
    await room.connect(url, token);

    await room.localParticipant.setMicrophoneEnabled(true);
  } catch (error) {
    callbacks.onError?.(error as Error);
    throw error;
  }

  return {
    room,
    disconnect: async () => {
      await room.disconnect();
    },
    setMuted: async (muted: boolean) => {
      await room.localParticipant.setMicrophoneEnabled(!muted);
    },
    isMuted: () => {
      const micPub = room.localParticipant.getTrackPublication(Track.Source.Microphone);
      return micPub ? micPub.isMuted : true;
    },
  };
}

export function cleanupAudioElements(): void {
  document.querySelectorAll("audio[id^='audio-']").forEach((el) => el.remove());
}
