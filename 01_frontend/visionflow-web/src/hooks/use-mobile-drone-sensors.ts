"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { MobileSensorSnapshot } from "@/types/mobile-telemetry";

type SensorStatus =
  | "IDLE"
  | "REQUESTING"
  | "ACTIVE"
  | "UNSUPPORTED"
  | "DENIED"
  | "ERROR";

type OrientationMode = "ABSOLUTE" | "RELATIVE" | "UNAVAILABLE";

interface DeviceOrientationEventWithCompass extends DeviceOrientationEvent {
  webkitCompassHeading?: number;
}

interface DeviceOrientationPermissionConstructor {
  requestPermission?: () => Promise<"granted" | "denied">;
}

interface UseMobileDroneSensorsResult {
  snapshot: MobileSensorSnapshot;
  status: SensorStatus;
  orientationMode: OrientationMode;
  secureContext: boolean | null;
  error: string | null;
  warning: string | null;
  start: () => Promise<boolean>;
  stop: () => void;
  getSnapshot: () => MobileSensorSnapshot;
}

const EMPTY_SNAPSHOT: MobileSensorSnapshot = {
  latitude: null,
  longitude: null,
  altitude: null,
  heading: null,
  pitch: null,
  roll: null,
  groundSpeed: null,
  horizontalAccuracy: null,
  verticalAccuracy: null,
  capturedAt: null,
};

function normalizeHeading(value: number): number {
  return ((value % 360) + 360) % 360;
}

function finiteOrNull(value: number | null): number | null {
  return value !== null && Number.isFinite(value) ? value : null;
}

export function useMobileDroneSensors(): UseMobileDroneSensorsResult {
  const [snapshot, setSnapshot] =
    useState<MobileSensorSnapshot>(EMPTY_SNAPSHOT);
  const [status, setStatus] = useState<SensorStatus>("IDLE");
  const [orientationMode, setOrientationMode] =
    useState<OrientationMode>("UNAVAILABLE");
  const [secureContext, setSecureContext] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  const snapshotRef = useRef<MobileSensorSnapshot>(EMPTY_SNAPSHOT);
  const geolocationWatchIdRef = useRef<number | null>(null);
  const orientationEventNameRef = useRef<string | null>(null);
  const orientationHandlerRef = useRef<EventListener | null>(null);
  const lastUiUpdateAtRef = useRef(0);

  const publishSnapshot = useCallback(
    (patch: Partial<MobileSensorSnapshot>, force = false) => {
      const next = {
        ...snapshotRef.current,
        ...patch,
      };

      snapshotRef.current = next;

      const now = Date.now();

      if (force || now - lastUiUpdateAtRef.current >= 200) {
        lastUiUpdateAtRef.current = now;
        setSnapshot(next);
      }
    },
    [],
  );

  const cleanupResources = useCallback(() => {
    if (geolocationWatchIdRef.current !== null) {
      navigator.geolocation.clearWatch(geolocationWatchIdRef.current);
      geolocationWatchIdRef.current = null;
    }

    if (
      orientationEventNameRef.current !== null &&
      orientationHandlerRef.current !== null
    ) {
      window.removeEventListener(
        orientationEventNameRef.current,
        orientationHandlerRef.current,
      );
    }

    orientationEventNameRef.current = null;
    orientationHandlerRef.current = null;
  }, []);

  const stop = useCallback(() => {
    cleanupResources();
    setStatus("IDLE");
    setError(null);
    setWarning(null);
  }, [cleanupResources]);

  const start = useCallback(async (): Promise<boolean> => {
    cleanupResources();
    setError(null);
    setWarning(null);
    setStatus("REQUESTING");

    const isSecure = window.isSecureContext;
    setSecureContext(isSecure);

    if (!isSecure) {
      setStatus("ERROR");
      setError(
        "스마트폰 GPS와 방향 센서는 HTTPS 보안 연결에서만 사용할 수 있습니다.",
      );
      return false;
    }

    if (!("geolocation" in navigator)) {
      setStatus("UNSUPPORTED");
      setError("이 브라우저는 위치 센서를 지원하지 않습니다.");
      return false;
    }

    let orientationGranted = true;
    const orientationConstructor = window.DeviceOrientationEvent as unknown as
      | DeviceOrientationPermissionConstructor
      | undefined;

    if (orientationConstructor?.requestPermission) {
      try {
        orientationGranted =
          (await orientationConstructor.requestPermission()) === "granted";
      } catch {
        orientationGranted = false;
      }
    }

    if (orientationGranted && "DeviceOrientationEvent" in window) {
      const absoluteSupported = "ondeviceorientationabsolute" in window;
      const eventName = absoluteSupported
        ? "deviceorientationabsolute"
        : "deviceorientation";

      const orientationHandler: EventListener = (event) => {
        const orientation = event as DeviceOrientationEventWithCompass;
        const compassHeading = orientation.webkitCompassHeading;
        const alpha = finiteOrNull(orientation.alpha);

        let heading: number | null = null;
        let mode: OrientationMode = "RELATIVE";

        if (
          compassHeading !== undefined &&
          Number.isFinite(compassHeading)
        ) {
          heading = normalizeHeading(compassHeading);
          mode = "ABSOLUTE";
        } else if (alpha !== null) {
          heading = normalizeHeading(360 - alpha);
          mode = orientation.absolute || absoluteSupported
            ? "ABSOLUTE"
            : "RELATIVE";
        }

        setOrientationMode(mode);
        publishSnapshot({
          heading,
          pitch: finiteOrNull(orientation.beta),
          roll: finiteOrNull(orientation.gamma),
        });
      };

      orientationEventNameRef.current = eventName;
      orientationHandlerRef.current = orientationHandler;
      window.addEventListener(eventName, orientationHandler);
    } else {
      setOrientationMode("UNAVAILABLE");
      setWarning(
        "방향 센서 권한이 없어 GPS 위치만 전송합니다. 브라우저 설정에서 동작 및 방향 접근을 허용할 수 있습니다.",
      );
    }

    geolocationWatchIdRef.current = navigator.geolocation.watchPosition(
      (position) => {
        const coordinates = position.coords;
        const movementHeading = finiteOrNull(coordinates.heading);
        const currentHeading = snapshotRef.current.heading;

        setStatus("ACTIVE");
        setError(null);
        publishSnapshot(
          {
            latitude: coordinates.latitude,
            longitude: coordinates.longitude,
            altitude: finiteOrNull(coordinates.altitude),
            heading: currentHeading ?? movementHeading,
            groundSpeed: finiteOrNull(coordinates.speed),
            horizontalAccuracy: finiteOrNull(coordinates.accuracy),
            verticalAccuracy: finiteOrNull(coordinates.altitudeAccuracy),
            capturedAt: position.timestamp,
          },
          true,
        );
      },
      (positionError) => {
        const denied = positionError.code === positionError.PERMISSION_DENIED;

        setStatus(denied ? "DENIED" : "ERROR");
        setError(
          denied
            ? "위치 권한이 거부되었습니다. 브라우저 사이트 권한에서 위치를 허용해 주세요."
            : `GPS 위치를 가져오지 못했습니다: ${positionError.message}`,
        );

        if (denied) {
          cleanupResources();
        }
      },
      {
        enableHighAccuracy: true,
        maximumAge: 1_000,
        timeout: 10_000,
      },
    );

    setStatus("ACTIVE");
    return true;
  }, [cleanupResources, publishSnapshot]);

  const getSnapshot = useCallback(() => snapshotRef.current, []);

  useEffect(() => {
    return () => {
      cleanupResources();
    };
  }, [cleanupResources]);

  return {
    snapshot,
    status,
    orientationMode,
    secureContext,
    error,
    warning,
    start,
    stop,
    getSnapshot,
  };
}
