# Extension guide

Extend one boundary at a time and keep the user-facing `intake v1.0` stable.

## Add an official source

1. Add a registry entry with authority, provider, dataset ID, credential reference, fixed host/path, supported property/trade combinations, and response format.
2. Add a collector that preserves raw responses, normalized JSON, a redacted request manifest, counts, timestamps, adapter version, and hashes.
3. Add a source-plan availability status. Never select a registry entry whose collector is only planned.
4. Add fixtures for success, zero result, partial coverage, authentication failure, schema change, and cancelled/corrected rows.

## Add a metric

Define its required lane, comparable filter, input artifact path, operation, unit, rounding, display value, and prohibited interpretation. Register the calculation and link every visible use to one claim.

## Add a property or transaction route

Specify the official dataset, price fields, area denominator, cancellation fields, comparable rule, current-market input, and unsupported claims. Do not reuse another property's endpoint because the fields look similar.

## Add a matching criterion

Use a stable candidate field and one documented operator. Keep must-have evaluation separate from equal-weight preference scoring. Add tests for true, false, missing, and malformed values.

## Add a report page

Only add a page when it answers a distinct customer question supported by evidence. Update the page-count validator and visual regression fixture. Do not shrink type to preserve a fixed count.
