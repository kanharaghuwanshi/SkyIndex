from __future__ import annotations

from datetime import datetime
from typing import Any


CONVENIENCE_FEE_CODES = {"CTF", "IBTF"}
SERVICE_FEE_CODES = {"SERVICE_FEE", "SVF", "SVCF"}


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _flight_number_from_identifier(identifier: dict[str, Any]) -> str | None:
    carrier = str(identifier.get("carrierCode") or "").strip()
    number = str(identifier.get("identifier") or "").strip()
    suffix = str(identifier.get("opSuffix") or "").strip()

    if carrier and number:
        return f"{carrier} {number}{suffix}"
    if number:
        return number
    return carrier or None


def _duration_minutes(start: str | None, end: str | None) -> int | None:
    if not start or not end:
        return None
    try:
        start_dt = datetime.fromisoformat(start)
        end_dt = datetime.fromisoformat(end)
        return int((end_dt - start_dt).total_seconds() // 60)
    except (TypeError, ValueError):
        return None


def _parse_segments(raw_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []

    for raw_segment in raw_segments or []:
        designator = raw_segment.get("designator") or {}
        identifier = raw_segment.get("identifier") or {}

        origin = designator.get("origin")
        destination = designator.get("destination")
        departure = designator.get("departure")
        arrival = designator.get("arrival")

        # SpiceJet exposes segment designator directly. The leg contains
        # equipment/terminal/operating-carrier data, so retain those where available.
        leg = (raw_segment.get("legs") or [{}])[0] or {}
        leg_designator = leg.get("designator") or {}
        leg_info = leg.get("legInfo") or {}

        origin = origin or leg_designator.get("origin")
        destination = destination or leg_designator.get("destination")
        departure = departure or leg_designator.get("departure") or leg_info.get("departureTime")
        arrival = arrival or leg_designator.get("arrival") or leg_info.get("arrivalTime")

        segment: dict[str, Any] = {
            "flight_number": _flight_number_from_identifier(identifier),
            "origin": origin,
            "destination": destination,
            "departure_time": departure,
            "arrival_time": arrival,
            "duration_minutes": _duration_minutes(departure, arrival),
            "aircraft": _first_present(leg_info, "equipmentType", "equipmentTypeSuffix"),
            "departure_terminal": leg_info.get("departureTerminal"),
            "arrival_terminal": leg_info.get("arrivalTerminal"),
            "operating_carrier": leg_info.get("operatingCarrier"),
            "segment_key": raw_segment.get("segmentKey"),
        }
        parsed.append(segment)

    return parsed


def _journey_flight_number(journey: dict[str, Any], segments: list[dict[str, Any]]) -> str | None:
    numbers = [s.get("flight_number") for s in segments if s.get("flight_number")]
    if numbers:
        return ", ".join(numbers)

    identifier = journey.get("identifier") or {}
    return _flight_number_from_identifier(identifier)


def _journey_times(journey: dict[str, Any], segments: list[dict[str, Any]]) -> tuple[str | None, str | None, int | None]:
    if segments:
        departure = segments[0].get("departure_time")
        arrival = segments[-1].get("arrival_time")
        duration = _duration_minutes(departure, arrival)
        if duration is not None:
            return departure, arrival, duration

    designator = journey.get("designator") or {}
    departure = designator.get("departure")
    arrival = designator.get("arrival")
    duration = _duration_minutes(departure, arrival)

    if duration is None:
        # Fallback only when journey-level strings are available.
        flight_duration = journey.get("flightDuration")
        if isinstance(flight_duration, str):
            hours = minutes = 0
            for token in flight_duration.split():
                if token.endswith("h"):
                    hours = int(token[:-1])
                elif token.endswith("m"):
                    minutes = int(token[:-1])
            duration = hours * 60 + minutes

    return departure, arrival, duration


def _extract_fare_details(
    fare_available: dict[str, Any],
) -> tuple[dict[str, Any], int | None]:
    passenger_fares = fare_available.get("passengerFares") or []
    if not passenger_fares:
        return {
            "base_fare": None,
            "taxes": None,
            "udf": None,
            "fees": None,
            "convenience_fee": None,
            "service_fee": None,
            "other_charges": None,
            "fee_breakdown": [],
            "tax_breakdown": [],
            "component_total": None,
            "breakdown_match": False,
        }, None

    # For the current one-adult search, ADT is the relevant passenger fare.
    passenger = next(
        (pf for pf in passenger_fares if pf.get("passengerType") == "ADT"),
        passenger_fares[0],
    )

    service_charges = passenger.get("serviceCharges") or []
    fee_breakdown: list[dict[str, Any]] = []
    tax_breakdown: list[dict[str, Any]] = []

    udf_total = 0.0
    other_fee_total = 0.0
    convenience_total = 0.0
    service_total = 0.0
    tax_total = 0.0
    has_udf = False
    has_fees = False
    has_taxes = False
    has_convenience = False
    has_service = False

    for charge in service_charges:
        charge_copy = {
            "code": charge.get("code"),
            "detail": charge.get("detail"),
            "type": charge.get("type"),
            "collect_type": charge.get("collectType", charge.get("collect_type")),
            "amount": _as_float(_first_present(charge, "amount", "foreignAmount")),
            "currency": charge.get("currencyCode", charge.get("currency", "INR")),
            "ticket_code": charge.get("ticketCode", charge.get("ticket_code")),
        }

        amount = charge_copy["amount"] or 0.0
        code = str(charge_copy["code"] or "").upper()
        charge_type = charge_copy["type"]

        if charge_type == 5:
            has_taxes = True
            tax_total += amount
            tax_breakdown.append(charge_copy)
        elif charge_type == 4:
            has_fees = True
            fee_breakdown.append(charge_copy)

            # UDF is kept separate and is NOT included in `fees`.
            if code == "UDF" or str(charge_copy["ticket_code"] or "").upper() == "UDF":
                has_udf = True
                udf_total += amount
            elif code in CONVENIENCE_FEE_CODES:
                has_convenience = True
                convenience_total += amount
                other_fee_total += amount
            elif code in SERVICE_FEE_CODES:
                has_service = True
                service_total += amount
                other_fee_total += amount
            else:
                other_fee_total += amount

    base_fare = _as_float(_first_present(passenger, "revenueFare", "publishedFare"))
    total_fare = _as_float(_first_present(passenger, "fareAmount"))

    taxes = tax_total if has_taxes else None
    udf = udf_total if has_udf else None
    fees = other_fee_total if has_fees else None
    convenience_fee = convenience_total if has_convenience else None
    service_fee = service_total if has_service else None

    # `other_charges` intentionally means non-UDF type-4 charges excluding
    # explicitly identified convenience/service fees.
    explicitly_identified = convenience_total + service_total
    other_charges = (
        max(0.0, other_fee_total - explicitly_identified)
        if has_fees
        else None
    )

    component_values = [base_fare, taxes, udf, fees]
    if all(value is not None for value in component_values):
        component_total = sum(component_values)  # type: ignore[arg-type]
        breakdown_match = total_fare is not None and abs(component_total - total_fare) < 0.01
    else:
        component_total = None
        breakdown_match = False

    return {
        "base_fare": base_fare,
        "taxes": taxes,
        "udf": udf,
        "fees": fees,
        "convenience_fee": convenience_fee,
        "service_fee": service_fee,
        "other_charges": other_charges,
        "fee_breakdown": fee_breakdown,
        "tax_breakdown": tax_breakdown,
        "component_total": component_total,
        "breakdown_match": breakdown_match,
    }, total_fare


def parse_availability_response(
    response: dict[str, Any],
    *,
    collection_date: str | None = None,
    collected_at: str | None = None,
    lead_time: int | None = None,
) -> list[dict[str, Any]]:
    """Convert the observed SpiceJet availability response into normalized quotes.

    Supports both direct and multi-segment journeys. Fare rows are kept per
    journey + fare family. Segment fares are NOT artificially split.
    """
    data = response.get("data") or {}
    trips = data.get("trips") or []
    all_quotes: list[dict[str, Any]] = []

    for trip in trips:
        trip_origin = trip.get("origin")
        trip_destination = trip.get("destination")
        journeys = trip.get("journeysAvailable") or []
        fares_available = data.get("faresAvailable") or {}

        for journey in journeys:
            raw_segments = journey.get("segments") or []
            segments = _parse_segments(raw_segments)

            origin = trip_origin or (segments[0].get("origin") if segments else None)
            destination = trip_destination or (segments[-1].get("destination") if segments else None)

            # Do not invent route/timing data if the source does not expose it.
            flight_number = _journey_flight_number(journey, segments)
            departure_time, arrival_time, duration_minutes = _journey_times(journey, segments)

            stops_raw = journey.get("stops")
            if stops_raw is None:
                stops = max(0, len(segments) - 1) if segments else None
            else:
                try:
                    stops = int(stops_raw)
                except (TypeError, ValueError):
                    stops = None

            fare_refs = journey.get("fares") or {}

            for fare_key, journey_fare in fare_refs.items():
                fare_available = fares_available.get(fare_key)
                if not isinstance(fare_available, dict):
                    # Some responses can embed enough fare metadata in the
                    # journey-level fare reference. Keep a row only when a
                    # complete amount/breakup is available.
                    continue

                details, total_fare = _extract_fare_details(fare_available)

                fare_code = fare_available.get("fareCode") or journey_fare.get("fareCode")
                fare_class = (
                    fare_available.get("classOfService")
                    or fare_available.get("fareClassOfService")
                    or journey_fare.get("classOfService")
                )
                availability = journey_fare.get("availableCount")
                if availability is None:
                    availability = fare_available.get("availableCount")

                if total_fare is None:
                    # We need an actual observed total fare for the normalized quote.
                    continue

                quote: dict[str, Any] = {
                    "origin": origin,
                    "destination": destination,
                    "travel_date": (
                        departure_time[:10]
                        if isinstance(departure_time, str) and len(departure_time) >= 10
                        else None
                    ),
                    "airline": "SpiceJet",
                    "flight_number": flight_number,
                    "departure_time": departure_time,
                    "arrival_time": arrival_time,
                    "duration_minutes": duration_minutes,
                    "stops": stops,
                    "segments": segments,
                    "fare_class": fare_class,
                    "fare_class_of_service": fare_available.get("fareClassOfService") or fare_class,
                    "product_class": fare_available.get("productClass"),
                    "fare_code": fare_code,
                    "availability": availability,
                    "base_fare": details["base_fare"],
                    "taxes": details["taxes"],
                    "udf": details["udf"],
                    "fees": details["fees"],
                    "convenience_fee": details["convenience_fee"],
                    "service_fee": details["service_fee"],
                    "other_charges": details["other_charges"],
                    "fee_breakdown": details["fee_breakdown"],
                    "tax_breakdown": details["tax_breakdown"],
                    "revenue_fare": details["base_fare"],
                    "published_fare": _as_float(
                        (fare_available.get("passengerFares") or [{}])[0].get("publishedFare")
                    ),
                    "discounted_fare": _as_float(
                        (fare_available.get("passengerFares") or [{}])[0].get("discountedFare")
                    ),
                    "total_fare": total_fare,
                    "currency": (
                        (details["fee_breakdown"][0].get("currency") if details["fee_breakdown"] else None)
                        or "INR"
                    ),
                    "source": "spicejet",
                    "collection_date": collection_date,
                    "collected_at": collected_at,
                    "lead_time": lead_time,
                    "journey_key": journey.get("journeyKey"),
                    "fare_availability_key": fare_key,
                    "segment_key": raw_segments[0].get("segmentKey") if raw_segments else None,
                    "operating_carrier": (
                        (raw_segments[0].get("legs") or [{}])[0]
                        .get("legInfo", {})
                        .get("operatingCarrier")
                        if raw_segments
                        else None
                    ),
                    "quote_key": f"spicejet:{origin}:{destination}:{flight_number}:{fare_code}:"
                    f"{departure_time[:10] if isinstance(departure_time, str) else None}",
                    "component_total": details["component_total"],
                    "breakdown_match": details["breakdown_match"],
                }

                # Keep the payload useful even if collection metadata was not
                # passed by a caller (e.g. offline parser tests).
                if quote["travel_date"] is None:
                    quote["travel_date"] = trip.get("travelDate")

                all_quotes.append(quote)

    return all_quotes


__all__ = ["parse_availability_response"]
