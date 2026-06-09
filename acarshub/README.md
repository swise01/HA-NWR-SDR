# ACARS Hub Add-on

Runs ACARS Hub as a local Home Assistant OS add-on for VDL2 messages received by the NUT Pi.

## Data Flow

```text
SDRTCP01 on NUT Pi
  -> dumpvdl2
      -> local Pi logs
      -> 10.0.1.100:5555/udp for this add-on
      -> feed.airframes.io:5552/udp for Airframes
```

Open the local dashboard at:

```text
http://10.0.1.100:8098
```

The add-on receives VDLM2 JSON on UDP port `5555`. ACARS, HFDL, Inmarsat, Iridium, and ADS-B overlays are disabled for now. Add them later by adding more decoders and enabling the relevant ACARS Hub environment variables.

ACARS Hub stores its database under the add-on's persistent `/data/acars` directory.
