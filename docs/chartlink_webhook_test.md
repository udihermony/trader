# Chartlink Webhook Testing Guide

## Overview

The Chartlink webhook now supports two types of payloads:
1. **Trading signals** - Single stock BUY/SELL orders
2. **Scan alerts** - Multiple stocks with trigger prices

## Test Scan Payload

```bash
curl -X POST http://localhost:8000/api/v1/webhooks/chartlink \
  -H "Content-Type: application/json" \
  -d '{
    "stocks": "SEPOWER,ASTEC,EDUCOMP",
    "trigger_prices": "3.75,541.8,2.1",
    "triggered_at": "2:34 pm",
    "scan_name": "Short term breakouts",
    "scan_url": "short-term-breakouts",
    "alert_name": "Alert for Short term breakouts",
    "webhook_url": "http://localhost:8000/api/v1/webhooks/chartlink"
  }'
```

## Test Trading Signal Payload

```bash
curl -X POST http://localhost:8000/api/v1/webhooks/chartlink \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "NSE:RELIANCE",
    "action": "BUY",
    "price": 2500.50,
    "quantity": 10,
    "message": "Buy signal for RELIANCE"
  }'
```

## View Recent Alerts

```bash
curl http://localhost:8000/api/v1/webhooks/alerts/recent?limit=10
```

## Expected Behavior

### Scan Alerts
- Status: `received` (not processed)
- Alert Type: `hold`
- Message: Contains scan_name or alert_name
- Metadata includes:
  - `is_scan_alert: true`
  - `scan_name`
  - `triggered_at`
  - `stocks`: Array of {symbol, trigger_price}
  - `raw_payload`: Original payload
  - `stocks_count`: Number of stocks

### Trading Signals
- Status: `received` → `processing` → `processed`
- Alert Type: Based on action (buy/sell/hold)
- Enqueued for trade processing
- Actual trades executed based on user strategies

## Key Changes

1. **Flexible webhook endpoint** - Automatically detects payload type
2. **Scan alert support** - Stores multiple stocks with metadata
3. **Idempotency** - Scans use consistent external_id based on scan_name + triggered_at
4. **Metadata preservation** - Full raw payload stored in metadata
5. **No trade processing** - Scan alerts marked as RECEIVED only, not processed
