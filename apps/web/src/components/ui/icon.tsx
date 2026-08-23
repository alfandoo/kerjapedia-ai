import { type ComponentProps } from "react";
import { cn } from "@/lib/utils";

type IconProps = ComponentProps<"svg"> & {
  size?: number | string;
  strokeWidth?: number | string;
};

export function Icon({
  className,
  size = 18,
  strokeWidth = 1.8,
  children,
  ...props
}: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      width={size}
      height={size}
      strokeWidth={strokeWidth}
      className={cn("shrink-0", className)}
      {...props}
    >
      {children}
    </svg>
  );
}
