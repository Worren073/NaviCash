import { createContext, useContext } from "react";

export const VoiceChatContext = createContext<{ openVoice: () => void }>({
  openVoice: () => {},
});

export function useVoiceChat() {
  return useContext(VoiceChatContext);
}
