# coding=utf-8
"""Preview notification content with new cards"""
import sys
sys.path.insert(0, '.')

from trendradar.core import load_config, load_frequency_words

config = load_config()

from trendradar.context import AppContext
ctx = AppContext(config)

# Get today's data (same flow as main program)
current_platform_ids = ctx.platform_ids
all_results, id_to_name, title_info = ctx.read_today_titles(current_platform_ids, quiet=True)

if not all_results:
    print('No data available')
    sys.exit(1)

total_titles = sum(len(titles) for titles in all_results.values())
print(f'Data: {len(all_results)} platforms, {total_titles} titles')

# Build stats via count_frequency (same as production)
word_groups, filter_words, global_filters = load_frequency_words()
new_titles = ctx.detect_new_titles(current_platform_ids, quiet=True)

stats, _ = ctx.count_frequency(
    all_results, word_groups, filter_words,
    id_to_name, title_info, new_titles,
    mode='current', global_filters=global_filters, quiet=True,
)
print(f'Stats: {len(stats)} keyword groups, {sum(s["count"] for s in stats)} matched titles')

# Prepare report data
report_data = ctx.prepare_report(stats, mode='current')
print(f'Report: {len(report_data["stats"])} groups, {sum(len(s["titles"]) for s in report_data["stats"])} titles')

# Split into batches (this triggers auto-generation of TL;DR, changes, cross-platform cards)
batches = ctx.split_content(report_data, 'feishu', mode='current', report_type='当前榜单')

print(f'\n{"="*60}')
print(f'FEISHU NOTIFICATION PREVIEW ({len(batches)} batches)')
print(f'{"="*60}')

for i, batch in enumerate(batches, 1):
    if len(batches) > 1:
        print(f'\n--- BATCH {i}/{len(batches)} ({len(batch)} chars) ---')
    if len(batch) > 4000:
        print(batch[:4000])
        print(f'... (truncated, total {len(batch)} chars)')
    else:
        print(batch)
