type IconProps = {
  className?: string;
};

export function ScaleIcon({ className }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 3v18" />
      <path d="M6 7h12" />
      <path d="M6 7l-3 8h6l-3-8z" />
      <path d="M18 7l-3 8h6l-3-8z" />
    </svg>
  );
}

export function SearchIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z" />
    </svg>
  );
}

export function ChatIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 5.5A3.5 3.5 0 0 1 7.5 2h9A3.5 3.5 0 0 1 20 5.5v5A3.5 3.5 0 0 1 16.5 14H12l-5 4v-4A3 3 0 0 1 4 11V5.5Z" />
    </svg>
  );
}

export function EditIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M13.5 6.5 17.5 10.5M5 19l3.4-.7L19 7.7a2.1 2.1 0 0 0-3-3L5.7 15 5 19Z" />
      <path d="M12 5H6a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-6" />
    </svg>
  );
}

export function CopyIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <rect x="8" y="8" width="11" height="11" rx="2" />
      <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
    </svg>
  );
}

export function ShareIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" />
      <path d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" />
    </svg>
  );
}

export function UserIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="8.5" r="3.2" />
      <path d="M5.5 19c.7-3.1 3-4.8 6.5-4.8s5.8 1.7 6.5 4.8" />
      <circle cx="12" cy="12" r="9.2" />
    </svg>
  );
}

export function TrashIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5" />
    </svg>
  );
}

export function SendIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="m4 11.5 15-7-4.8 15-3.2-6.3L4 11.5Zm7 1.7 3.1-3.1" />
    </svg>
  );
}

export function StopIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 7h10v10H7z" />
    </svg>
  );
}

export function FileIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 3h7l4 4v14H7V3Zm7 0v5h5M9 13h6M9 17h6" />
    </svg>
  );
}

export function ThumbsUpIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 11v9H4v-9h3Zm0 0 5-8 1 1v5h5.2a2 2 0 0 1 2 2.3l-1 6A2 2 0 0 1 17.2 19H7" />
    </svg>
  );
}

export function ThumbsDownIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 13V4H4v9h3Zm0 0 5 8 1-1v-5h5.2a2 2 0 0 0 2-2.3l-1-6A2 2 0 0 0 17.2 5H7" />
    </svg>
  );
}

export function AlertIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 8v5m0 4h.01M10.3 4.8 2.8 18a2 2 0 0 0 1.7 3h15a2 2 0 0 0 1.7-3L13.7 4.8a2 2 0 0 0-3.4 0Z" />
    </svg>
  );
}

export function ExternalIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M14 4h6v6M20 4l-9 9M20 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5" />
    </svg>
  );
}

export function UploadIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v5h14v-5" />
    </svg>
  );
}

export function DatabaseIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 6c0-2 3.6-3 8-3s8 1 8 3-3.6 3-8 3-8-1-8-3Zm0 0v6c0 2 3.6 3 8 3s8-1 8-3V6M4 12v6c0 2 3.6 3 8 3s8-1 8-3v-6" />
    </svg>
  );
}

export function RefreshIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M20 7v5h-5M4 17v-5h5M18.5 9A7 7 0 0 0 6 7M5.5 15A7 7 0 0 0 18 17" />
    </svg>
  );
}

export function PlayIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="m8 5 11 7-11 7V5Z" />
    </svg>
  );
}

export function MoreIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 5h.01M12 12h.01M12 19h.01" />
    </svg>
  );
}

export function ChartIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 20h16M6 16V9m4 7V5m4 11v-5m4 5v-8" />
    </svg>
  );
}

export function CheckIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="m5 12 4 4L19 6" />
    </svg>
  );
}

export function LogoutIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4m7 14 5-5-5-5m5 5H9" />
    </svg>
  );
}

export function ChevronLeftIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="m15 18-6-6 6-6" />
    </svg>
  );
}

export function SettingsIcon({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7ZM19 13.5l2-1.5-2-1.5-.5-2 1-2.2-2.3-1-1.6 1.2-2.1-.8L12 3l-1.5 2.7-2.1.8-1.6-1.2-2.3 1 1 2.2-.5 2L3 12l2 1.5.5 2-1 2.2 2.3 1 1.6-1.2 2.1.8L12 21l1.5-2.7 2.1-.8 1.6 1.2 2.3-1-1-2.2.5-2Z" />
    </svg>
  );
}
