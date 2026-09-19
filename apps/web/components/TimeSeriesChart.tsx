'use client';

import ReactECharts from 'echarts-for-react';
import { useMemo } from 'react';
import { PROVENANCE_STYLE } from '@/lib/format';
import { ProvenanceBadge } from './ProvenanceBadge';
import type { Provenance, Series } from '@/lib/types';

/**
 * One chart component for the whole app.
 *
 * Series are coloured by *provenance*, not by an arbitrary palette: measured is
 * green, predicted is blue, simulated is violet, injected is pink. After thirty
 * seconds with the app the colour alone tells an operator whether they are
 * looking at something that happened or something a model believes.
 */

export interface ChartSeriesConfig {
  series: Series;
  type?: 'line' | 'bar';
  colour?: string;
  dashed?: boolean;
  width?: number;
  area?: boolean;
  yAxisIndex?: number;
  showBand?: boolean;
  opacity?: number;
}

const PROV_COLOUR: Record<string, string> = {
  MEASURED: '#22c55e',
  PREDICTED: '#3b9dfb',
  SIMULATED: '#a78bfa',
  OPTIMISED: '#00e08a',
  DERIVED: '#f5a524',
  INJECTED: '#f472b6',
};

export function TimeSeriesChart({
  configs,
  height = 280,
  yAxisName,
  y2AxisName,
  markLineValue,
  markLineLabel,
  markAreaFrom,
  markAreaTo,
  markAreaLabel,
  cursorTime,
  legend = true,
  yScale = false,
  y2Scale = true,
}: {
  configs: ChartSeriesConfig[];
  height?: number;
  yAxisName?: string;
  y2AxisName?: string;
  markLineValue?: number;
  markLineLabel?: string;
  markAreaFrom?: string;
  markAreaTo?: string;
  markAreaLabel?: string;
  cursorTime?: string;
  legend?: boolean;
  /** Let the axis pick its own base. Temperatures squash to a sliver from 0. */
  yScale?: boolean;
  y2Scale?: boolean;
}) {
  const option = useMemo(() => {
    const series: Record<string, unknown>[] = [];

    configs.forEach((config, index) => {
      const colour = config.colour ?? PROV_COLOUR[config.series.provenance.source_type] ?? '#94a3b8';
      const data = config.series.timestamps.map((timestamp, i) => [
        timestamp,
        config.series.values[i] ?? null,
      ]);

      // Interval bands are drawn as a transparent floor plus a stacked ribbon:
      // ECharts has no first-class band, and this keeps tooltips honest.
      if (config.showBand && config.series.lower && config.series.upper) {
        const stackId = `band-${index}`;
        series.push({
          name: `${config.series.label} lower`,
          type: 'line',
          stack: stackId,
          data: config.series.timestamps.map((timestamp, i) => [
            timestamp,
            config.series.lower?.[i] ?? null,
          ]),
          lineStyle: { opacity: 0 },
          areaStyle: { color: 'transparent', opacity: 0 },
          symbol: 'none',
          silent: true,
          legendHoverLink: false,
          tooltip: { show: false },
          z: 1,
        });
        series.push({
          name: `${config.series.label} interval`,
          type: 'line',
          stack: stackId,
          data: config.series.timestamps.map((timestamp, i) => {
            const lower = config.series.lower?.[i];
            const upper = config.series.upper?.[i];
            return [timestamp, lower === null || upper === null || lower === undefined || upper === undefined ? null : upper - lower];
          }),
          lineStyle: { opacity: 0 },
          areaStyle: { color: colour, opacity: 0.13 },
          symbol: 'none',
          silent: true,
          legendHoverLink: false,
          tooltip: { show: false },
          z: 1,
        });
      }

      series.push({
        name: config.series.label,
        type: config.type ?? 'line',
        data,
        yAxisIndex: config.yAxisIndex ?? 0,
        smooth: false,
        symbol: 'none',
        connectNulls: false,
        z: 3,
        itemStyle: { color: colour },
        lineStyle: {
          color: colour,
          width: config.width ?? 1.6,
          type: config.dashed ? 'dashed' : 'solid',
          opacity: config.opacity ?? 1,
        },
        areaStyle: config.area
          ? {
              color: {
                type: 'linear',
                x: 0,
                y: 0,
                x2: 0,
                y2: 1,
                colorStops: [
                  { offset: 0, color: `${colour}33` },
                  { offset: 1, color: `${colour}00` },
                ],
              },
            }
          : undefined,
        markLine:
          index === 0 && (markLineValue !== undefined || cursorTime)
            ? {
                silent: true,
                symbol: 'none',
                data: [
                  ...(markLineValue !== undefined
                    ? [
                        {
                          yAxis: markLineValue,
                          lineStyle: { color: '#f4404b', type: 'dashed', width: 1.2 },
                          label: {
                            formatter: markLineLabel ?? '',
                            color: '#f4404b',
                            fontSize: 10,
                            position: 'insideEndTop',
                          },
                        },
                      ]
                    : []),
                  ...(cursorTime
                    ? [
                        {
                          xAxis: cursorTime,
                          lineStyle: { color: '#00e08a', width: 1.2 },
                          label: { show: false },
                        },
                      ]
                    : []),
                ],
              }
            : undefined,
        markArea:
          index === 0 && markAreaFrom && markAreaTo
            ? {
                silent: true,
                itemStyle: { color: 'rgba(244, 114, 182, 0.09)' },
                label: {
                  show: Boolean(markAreaLabel),
                  formatter: markAreaLabel ?? '',
                  color: '#f472b6',
                  fontSize: 10,
                  position: 'insideTop',
                },
                data: [[{ xAxis: markAreaFrom }, { xAxis: markAreaTo }]],
              }
            : undefined,
      });
    });

    const yAxes = [
      {
        type: 'value',
        name: yAxisName,
        // A kW axis reads better from zero; a temperature axis does not.
        scale: yScale,
        nameGap: 12,
        nameTextStyle: { color: '#6b7a8d', fontSize: 10, align: 'left' },
        axisLabel: { color: '#6b7a8d', fontSize: 10 },
        splitLine: { lineStyle: { color: 'rgba(38,50,63,0.55)', type: 'dashed' } },
        axisLine: { show: false },
      },
    ];
    if (y2AxisName) {
      yAxes.push({
        type: 'value',
        name: y2AxisName,
        scale: y2Scale,
        nameGap: 12,
        nameTextStyle: { color: '#6b7a8d', fontSize: 10, align: 'right' },
        axisLabel: { color: '#6b7a8d', fontSize: 10 },
        splitLine: { show: false } as never,
        axisLine: { show: false },
      } as never);
    }

    return {
      backgroundColor: 'transparent',
      animationDuration: 260,
      grid: { left: 52, right: y2AxisName ? 52 : 16, top: legend ? 34 : 18, bottom: 24 },
      legend: legend
        ? {
            show: true,
            top: 0,
            right: 8,
            icon: 'roundRect',
            itemWidth: 9,
            itemHeight: 3,
            textStyle: { color: '#94a3b8', fontSize: 10 },
            data: configs.map((c) => c.series.label),
          }
        : { show: false },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(8,11,17,0.96)',
        borderColor: '#26323f',
        borderWidth: 1,
        textStyle: { color: '#e8eef5', fontSize: 11 },
        axisPointer: { type: 'line', lineStyle: { color: '#3a4655' } },
      },
      xAxis: {
        type: 'time',
        axisLabel: { color: '#6b7a8d', fontSize: 10, hideOverlap: true },
        axisLine: { lineStyle: { color: '#26323f' } },
        splitLine: { show: false },
      },
      yAxis: yAxes,
      series,
    };
  }, [
    configs,
    yAxisName,
    y2AxisName,
    markLineValue,
    markLineLabel,
    markAreaFrom,
    markAreaTo,
    markAreaLabel,
    cursorTime,
    legend,
    yScale,
    y2Scale,
  ]);

  return (
    <ReactECharts
      option={option}
      style={{ height, width: '100%' }}
      opts={{ renderer: 'canvas' }}
      notMerge
      lazyUpdate
    />
  );
}

export function SeriesLegend({ items }: { items: { label: string; provenance: Provenance }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
      {items.map((item) => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          <span
            className="h-0.5 w-4 rounded"
            style={{
              backgroundColor:
                PROV_COLOUR[item.provenance.source_type] ??
                PROVENANCE_STYLE[item.provenance.source_type].text,
            }}
          />
          <span className="text-2xs text-ink-300">{item.label}</span>
          <ProvenanceBadge provenance={item.provenance} size="xs" showLabel={false} />
        </span>
      ))}
    </div>
  );
}
