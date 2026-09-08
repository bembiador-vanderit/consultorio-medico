import React from "react";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
}

export function Card({ children, className = "", ...props }: CardProps) {
  const baseClasses =
    "rounded-[var(--radius-lg)] bg-[var(--atlas-surface)] border border-[var(--atlas-border)] shadow-[var(--atlas-shadow-sm)] p-6";

  return (
    <div className={`${baseClasses} ${className}`} {...props}>
      {children}
    </div>
  );
}
