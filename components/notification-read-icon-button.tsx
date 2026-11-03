"use client";

type NotificationReadIconButtonProps={
  onClick:()=>void;
  label:string;
  disabled?:boolean;
};

/** Shared icon-only 'mark all read' action for admin, customer and reseller. */
export function NotificationReadIconButton({onClick,label,disabled=false}:NotificationReadIconButtonProps){
  return <button
    type="button"
    className="notificationReadIconButton"
    onClick={onClick}
    disabled={disabled}
    title={label}
    aria-label={label}
  >
    <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12Z"/>
      <circle cx="12" cy="12" r="3"/>
      <path d="m16.5 19 2.1 2.1 3.3-3.5"/>
    </svg>
  </button>;
}
