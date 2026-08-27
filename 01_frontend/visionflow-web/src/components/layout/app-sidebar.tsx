"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  getVisibleNavigationItems,
  isNavigationItemActive,
} from "@/components/layout/navigation-items";
import type { OperatorSecurityStatus } from "@/types/operator-security";

interface AppSidebarProps {
  operatorSecurity: OperatorSecurityStatus | null;
}

function resolveDesktopLinkClassName(
  active: boolean,
  presentation: boolean,
) {
  return [
    "vf-sidebar-link",
    presentation ? "vf-sidebar-link--presentation" : "",
    active ? "is-active" : "",
  ]
    .filter(Boolean)
    .join(" ");
}

export function AppSidebar({ operatorSecurity }: AppSidebarProps) {
  const pathname = usePathname();
  const visibleItems = getVisibleNavigationItems(operatorSecurity);

  return (
    <aside className="vf-command-sidebar hidden w-60 shrink-0 lg:block">
      <div className="vf-command-sidebar__inner">
        <div className="vf-command-brand">
          <div className="vf-command-brand__row">
            <span aria-hidden="true" className="vf-command-brand__mark">
              VF
            </span>
            <div>
              <p className="vf-command-brand__kicker">VisionFlow</p>
              <p className="vf-command-brand__title">Command Center</p>
            </div>
          </div>
          <p className="vf-command-brand__description">
            Intelligent Drone Operations
            <br />
            &amp; Safety Monitoring
          </p>
        </div>

        <nav aria-label="주요 메뉴">
          <p className="vf-sidebar-section-label">Mission navigation</p>
          <ul className="vf-sidebar-list">
            {visibleItems.map((item) => {
              const active = isNavigationItemActive(
                pathname,
                item.href,
                item.activeAliases,
              );
              const presentation = item.presentation === true;

              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={resolveDesktopLinkClassName(
                      active,
                      presentation,
                    )}
                  >
                    <span
                      aria-hidden="true"
                      className="vf-sidebar-link__indicator"
                    />
                    {presentation ? (
                      <span aria-hidden="true">▶</span>
                    ) : null}
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="vf-sidebar-emblem">
          <div className="vf-sidebar-emblem__frame">
            <Image
                src="/branding/emblem.png"
                alt="PyvaOps Team Emblem"
                width={2048}
                height={1117}
                sizes="196px"
                className="vf-sidebar-emblem__image"
                draggable={false}
            />
          </div>
        </div>
        <footer className="vf-sidebar-runtime">
          <p className="vf-sidebar-runtime__label">Runtime profile</p>
          <p className="vf-sidebar-runtime__value">
            Phase 3 · Edge Operations
          </p>
          <p className="vf-sidebar-runtime__meta">
            Team PyvaOps
            <br />
            Command UI Foundation 1A
          </p>
        </footer>
      </div>
    </aside>
  );
}
