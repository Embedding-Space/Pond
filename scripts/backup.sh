#!/bin/sh
# Pond backup script for Raspberry Pi deployment
# Runs hourly, uploads to B2, maintains 72-hour retention

set -e

echo "Pond backup service starting..."

# Install b2 CLI if not present
if ! command -v b2 > /dev/null 2>&1; then
    echo "Installing B2 CLI..."
    apk add --no-cache python3 py3-pip
    pip3 install --break-system-packages b2
fi

# Authorize with B2
echo "Authorizing with B2..."
b2 account authorize "$B2_APPLICATION_KEY_ID" "$B2_APPLICATION_KEY"

echo "Backup service initialized. Starting hourly backup loop..."

while true; do
    # Calculate sleep time to next hour
    now=$(date +%s)
    next_hour=$(((now / 3600 + 1) * 3600))
    sleep_seconds=$((next_hour - now))

    next_time=$(date -d "@$next_hour" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || date -r "$next_hour" "+%Y-%m-%d %H:%M:%S")
    echo "Next backup in $sleep_seconds seconds (at $next_time)"
    sleep "$sleep_seconds"

    # Create timestamp for this backup
    timestamp=$(date +%Y%m%d-%H%M%S)
    backup_file="/tmp/pond-${timestamp}.sql"
    remote_path="backups/pond-${timestamp}.sql"

    echo "Starting backup at $(date)"

    # Dump the pond database
    if pg_dump -h postgres -U "${POSTGRES_USER:-postgres}" -d pond > "$backup_file"; then
        echo "Database dump completed: $(du -h "$backup_file" | cut -f1)"

        # Upload to B2
        if b2 file upload "$B2_BUCKET_NAME" "$backup_file" "$remote_path"; then
            echo "Uploaded to B2: $remote_path"

            # Remove local file
            rm "$backup_file"
            echo "Removed local backup file"

            # Clean up old backups (keep last 72)
            echo "Cleaning up old backups..."
            b2 ls "b2://$B2_BUCKET_NAME/backups/" | \
                grep -E 'backups/pond-[0-9]{8}-[0-9]{6}\.sql$' | \
                sort | \
                head -n -72 | \
                while read -r filepath; do
                    if [ -n "$filepath" ]; then
                        echo "Deleting old backup: $filepath"
                        b2 rm "b2://$B2_BUCKET_NAME/$filepath" || true
                    fi
                done

            echo "Backup cycle completed successfully"
        else
            echo "ERROR: Failed to upload to B2"
            rm "$backup_file"
        fi
    else
        echo "ERROR: Database dump failed"
    fi

    echo "---"
done
