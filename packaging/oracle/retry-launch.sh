#!/usr/bin/env bash
# Keep retrying to launch the Always-Free ARM VM until Oracle has capacity.
#
# Run it in ORACLE CLOUD SHELL (the >_ icon, top-right of the console) — the OCI
# CLI there is preinstalled AND already authenticated, so there's nothing to set
# up. It discovers your AD / subnet / image automatically and loops the launch.
#
#   curl -fsSL https://raw.githubusercontent.com/omri566/garmin-coach/main/packaging/oracle/retry-launch.sh -o retry.sh
#   bash retry.sh
#
# Leave it running; when a slot frees up it launches the VM and prints the IP.
set -uo pipefail

# ---- settings (override by exporting before running) ----
NAME="${NAME:-garmin-instance}"
SHAPE="VM.Standard.A1.Flex"
OCPUS="${OCPUS:-1}"            # 1 core is easier to get than 4; you can resize later
MEM_GB="${MEM_GB:-6}"
VCN_NAME="${VCN_NAME:-garmin-vcn}"
OS="Canonical Ubuntu"
OS_VER="22.04"
SLEEP="${SLEEP:-60}"          # seconds between attempts
KEY="$HOME/.ssh/garmin_coach"

# ---- compartment = tenancy root ----
COMPARTMENT="${OCI_TENANCY:-}"
if [ -z "$COMPARTMENT" ]; then
  read -rp "Paste your tenancy (root compartment) OCID [Profile menu → Tenancy → OCID]: " COMPARTMENT
fi

echo "→ discovering availability domain / subnet / image…"
AD=$(oci iam availability-domain list -c "$COMPARTMENT" --query 'data[0].name' --raw-output)
VCN_ID=$(oci network vcn list -c "$COMPARTMENT" --display-name "$VCN_NAME" --query 'data[0].id' --raw-output)
SUBNET_ID=$(oci network subnet list -c "$COMPARTMENT" --vcn-id "$VCN_ID" \
            --query "data[?contains(\"display-name\", 'public')].id | [0]" --raw-output)
IMAGE_ID=$(oci compute image list -c "$COMPARTMENT" \
            --operating-system "$OS" --operating-system-version "$OS_VER" \
            --shape "$SHAPE" --sort-by TIMECREATED --sort-order DESC \
            --query 'data[0].id' --raw-output)

for v in AD VCN_ID SUBNET_ID IMAGE_ID; do
  val="${!v}"
  [ -n "$val" ] && [ "$val" != "null" ] || { echo "!! couldn't resolve $v — is the VCN '$VCN_NAME' in this region?"; exit 1; }
done

# ---- SSH key (generated once, here in Cloud Shell) ----
[ -f "$KEY" ] || ssh-keygen -t rsa -b 2048 -N "" -f "$KEY" >/dev/null
echo "→ AD=$AD"
echo "→ subnet=$SUBNET_ID"
echo "→ image=$IMAGE_ID"
echo "→ ssh key=$KEY (private key stays in Cloud Shell)"
echo "→ launching every ${SLEEP}s until capacity is available… (Ctrl-C to stop)"

n=0
while true; do
  n=$((n + 1))
  RES=$(oci compute instance launch \
        --availability-domain "$AD" \
        --compartment-id "$COMPARTMENT" \
        --shape "$SHAPE" \
        --shape-config "{\"ocpus\":$OCPUS,\"memoryInGBs\":$MEM_GB}" \
        --image-id "$IMAGE_ID" \
        --subnet-id "$SUBNET_ID" \
        --assign-public-ip true \
        --display-name "$NAME" \
        --ssh-authorized-keys-file "$KEY.pub" 2>&1)

  if echo "$RES" | grep -q 'ocid1.instance'; then
    ID=$(echo "$RES" | grep -oE 'ocid1\.instance[^"]+' | head -1)
    echo "✅ LAUNCHED after $n tries — $ID"
    echo "   waiting ~40s for the public IP…"
    sleep 40
    IP=$(oci compute instance list-vnics --instance-id "$ID" --query 'data[0]."public-ip"' --raw-output 2>/dev/null)
    echo
    echo "   PUBLIC IP : ${IP:-"(open the instance in the console to see it)"}"
    echo "   SSH from Cloud Shell:  ssh -i $KEY ubuntu@${IP:-<ip>}"
    break
  elif echo "$RES" | grep -qiE "capacity"; then
    echo "[$n] $(date +%H:%M:%S) out of capacity — retry in ${SLEEP}s"
    sleep "$SLEEP"
  elif echo "$RES" | grep -qiE "TooManyRequests|429|rate"; then
    echo "[$n] rate limited — backing off $((SLEEP * 2))s"
    sleep $((SLEEP * 2))
  else
    echo "!! launch failed for a non-capacity reason — showing it so we can fix:"
    echo "$RES"
    exit 1
  fi
done
