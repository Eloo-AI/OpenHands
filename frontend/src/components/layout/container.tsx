import clsx from "clsx";
import React from "react";
import { NavTab } from "./nav-tab";

interface ContainerProps {
  label?: React.ReactNode;
  labels?: {
    label: string | React.ReactNode;
    to: string;
    icon?: React.ReactNode;
    isBeta?: boolean;
    isLoading?: boolean;
    rightContent?: React.ReactNode;
  }[];
  children: React.ReactNode;
  className?: React.HTMLAttributes<HTMLDivElement>["className"];
}

export function Container({
  label,
  labels,
  children,
  className,
}: ContainerProps) {
  return (
    <div
      className={clsx(
        "bg-base-secondary border border-neutral-600 rounded-xl flex flex-col h-full",
        className,
      )}
    >
      {labels && (
        <div className="flex text-xs h-[36px]">
          {labels.map(
            ({ label: l, to, icon, isBeta, isLoading, rightContent }) => (
              <NavTab
                key={to}
                to={to}
                label={l}
                icon={icon}
                isBeta={isBeta}
                isLoading={isLoading}
                rightContent={rightContent}
              />
            ),
          )}
        </div>
      )}
      {!labels && label && (
        <div className="px-2 h-[36px] border-b border-neutral-600 text-xs flex items-center">
          {label}
        </div>
      )}
      <div className="overflow-hidden flex-grow rounded-b-xl">{children}</div>
    </div>
  );
}
