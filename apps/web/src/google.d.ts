interface GoogleAccountsIdCallbackResponse {
  credential?: string;
  select_by?: string;
}

interface GoogleAccountsId {
  initialize: (config: {
    client_id: string;
    callback: (response: GoogleAccountsIdCallbackResponse) => void;
    auto_select?: boolean;
    cancel_on_tap_outside?: boolean;
    context?: string;
  }) => void;
  prompt: (options?: { one_tap?: boolean }) => void;
  renderButton: (
    parent: HTMLElement,
    options?: Record<string, unknown>
  ) => void;
  disableAutoSelect: () => void;
  cancel: () => void;
}

interface GoogleAccounts {
  id: GoogleAccountsId;
}

interface Window {
  google?: {
    accounts?: GoogleAccounts;
  };
}
