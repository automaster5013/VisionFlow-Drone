"use client";

import { useEffect } from "react";
import { useMap } from "react-leaflet";

interface MapPositionControllerProps {
    latitude: number;
    longitude: number;
    zoom?: number;
}

export function MapPositionController({
                                          latitude,
                                          longitude,
                                          zoom = 16,
                                      }: MapPositionControllerProps) {
    const map = useMap();

    useEffect(() => {
        map.flyTo(
            [latitude, longitude],
            zoom,
            {
                animate: true,
                duration: 1,
            },
        );
    }, [
        latitude,
        longitude,
        map,
        zoom,
    ]);

    return null;
}