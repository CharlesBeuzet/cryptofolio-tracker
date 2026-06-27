export default function Logo({ className = '' }: { className?: string }) {
  return (
    <svg width="22" height="28" viewBox="0 0 24 30" className={`drop-shadow-[0_0_5px_rgba(79,190,134,0.7)] ${className}`}>
      <path fill="var(--green)" d="M13 1 L4 25 L22 25 Z" />
      <path stroke="var(--green)" d="M2 27.5 L23 27.5" strokeWidth="1.6" fill="none" />
    </svg>
  )
}
