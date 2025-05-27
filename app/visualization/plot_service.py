# app/visualization/plot_service.py
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import matplotlib as mpl
import pandas as pd
from datetime import datetime
from typing import List, Dict, Any, Optional # Dict and Any not directly used in PlottingService methods but common
import logging

from app.models import ProcessedDataset, FredDataPoint, VisualizationSpec
from app.services.fred_service import FredService # For recession data

logger = logging.getLogger(__name__)

# Apply base styling
# plt.style.use('seaborn-v0_8-whitegrid') # Original style
plt.xkcd() # Apply XKCD style

# Set fonts suitable for XKCD style
# Note: 'Humor Sans' and 'Comic Neue' are ideal but might not be installed.
# 'Comic Sans MS' is a common fallback. 'cursive' or 'fantasy' are generic.
mpl.rcParams['font.family'] = 'xkcd' # Often set by plt.xkcd() itself, but good to be explicit
mpl.rcParams['font.sans-serif'] = ['Humor Sans', 'Comic Neue', 'Comic Sans MS', 'cursive', 'fantasy']
mpl.rcParams['axes.labelsize'] = 11
mpl.rcParams['axes.titlesize'] = 14
mpl.rcParams['xtick.labelsize'] = 10
mpl.rcParams['ytick.labelsize'] = 10
mpl.rcParams['figure.dpi'] = 100 # Default DPI


def format_large_number(x, pos=None): # pos is unused but often part of FuncFormatter signature
    if abs(x) >= 1e12: return f'{x/1e12:.1f}T'
    if abs(x) >= 1e9: return f'{x/1e9:.1f}B'
    if abs(x) >= 1e6: return f'{x/1e6:.1f}M'
    if abs(x) >= 1e3: return f'{x/1e3:.1f}K'
    return f'{x:,.0f}' # Default to comma-separated integer if not large

def highlight_recessions(ax: plt.Axes, start_date_dt: datetime, end_date_dt: datetime, fred_service_for_recessions: FredService):
    logger.info(f"Attempting to fetch recession data between {start_date_dt} and {end_date_dt}")
    # Convert datetime to string for FRED service
    start_str = start_date_dt.strftime('%Y-%m-%d')
    end_str = end_date_dt.strftime('%Y-%m-%d')

    # Fetch USREC data (1 for recession, 0 otherwise)
    recessions_data_series = fred_service_for_recessions.get_series_data('USREC', start_str, end_str)

    if recessions_data_series is None or recessions_data_series.empty:
        logger.info("No recession data found for the given period.")
        return

    # Convert to DataFrame for easier manipulation
    recessions_df = pd.DataFrame({'date': recessions_data_series.index, 'value': recessions_data_series.values})
    recessions_df['date'] = pd.to_datetime(recessions_df['date'])
    recessions_df = recessions_df.set_index('date').sort_index() # Ensure sorted
    
    # Identify recession periods
    in_recession = False
    rec_start_date = None
    shaded_once = False # To ensure legend item is added only once

    # Iterate through a continuous date range to correctly identify gaps if data is sparse
    # For FRED USREC, data is usually monthly, so reindexing to daily helps find precise start/end
    # However, for simple shading, iterating through available points is often sufficient if dense enough
    
    # Simpler iteration for existing points, good if data is monthly/quarterly
    # For more robust span detection with sparse data, one might reindex to daily and ffill
    
    for date, row in recessions_df.iterrows():
        if row['value'] == 1 and not in_recession:
            in_recession = True
            rec_start_date = date
        elif row['value'] == 0 and in_recession:
            in_recession = False
            if rec_start_date:
                ax.axvspan(rec_start_date, date, color='grey', alpha=0.2, label='_nolegend_')
                shaded_once = True
                rec_start_date = None
    
    if in_recession and rec_start_date: # If series ends during a recession
        ax.axvspan(rec_start_date, recessions_df.index.max(), color='grey', alpha=0.2, label='_nolegend_')
        shaded_once = True

    # Ensure legend for recession is added only once if any shading was done
    if shaded_once:
        # Check if "Recession" label already exists to prevent duplicates if highlight_recessions is called multiple times on same ax
        handles, labels = ax.get_legend_handles_labels()
        if "Recession" not in labels:
            # Add a dummy patch for the legend
            ax.fill_between([], [], color='grey', alpha=0.2, label='Recession')


class PlottingService:
    def __init__(self, fred_service: FredService):
        if not fred_service:
            logger.error("PlottingService initialized without a FredService instance (needed for recession data).")
            raise ValueError("FredService instance is required for PlottingService.")
        self.fred_service = fred_service


    def _prepare_plot_data(self, data_points: List[FredDataPoint]) -> pd.Series:
        if not data_points:
            return pd.Series(dtype=float)
        dates = [pd.to_datetime(dp.date) for dp in data_points if dp.date is not None]
        values = [dp.value for dp in data_points if dp.date is not None] # Ensure value corresponds to a valid date
        
        if not dates: # If all dates were None
             return pd.Series(dtype=float)

        series = pd.Series(values, index=dates).sort_index()
        return series

    def create_line_chart(self, datasets: List[ProcessedDataset], spec: VisualizationSpec) -> plt.Figure:
        fig, ax = plt.subplots(figsize=spec.options.get("figsize", (10, 6)))

        min_date_overall, max_date_overall = None, None

        for i, dataset in enumerate(datasets):
            if not dataset.data_points:
                logger.warning(f"Dataset '{dataset.name}' has no data points. Skipping.")
                continue

            series = self._prepare_plot_data(dataset.data_points)
            if series.empty:
                logger.warning(f"Pandas series for '{dataset.name}' is empty after preparation. Skipping.")
                continue
            
            # Update min/max dates for x-axis and recession shading
            current_min_date = series.index.min()
            current_max_date = series.index.max()

            if min_date_overall is None or current_min_date < min_date_overall: 
                min_date_overall = current_min_date
            if max_date_overall is None or current_max_date > max_date_overall: 
                max_date_overall = current_max_date

            line_label = dataset.metadata.get("plot_label", dataset.name) # Allow custom label
            ax.plot(series.index, series.values, label=line_label, linewidth=spec.options.get("linewidth", 1.5))

        ax.set_title(spec.title or "Line Chart", fontweight='bold', pad=15)
        ax.set_xlabel(spec.x_axis_label or 'Date', labelpad=10)
        ax.set_ylabel(spec.y_axis_label or 'Value', labelpad=10)

        # Formatting Y-axis
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(format_large_number))

        # Formatting X-axis (date formatting)
        if min_date_overall and max_date_overall:
            date_range_days = (max_date_overall - min_date_overall).days
            if date_range_days > 365 * 5:  # More than 5 years
                ax.xaxis.set_major_locator(mdates.YearLocator(base=max(1, date_range_days // (365 * 5)))) # Aim for ~5-10 ticks
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
            elif date_range_days > 365: # 1-5 years
                ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
                ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
            else: # Less than a year
                ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=10))
                ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))
            
            ax.set_xlim([min_date_overall, max_date_overall]) # Ensure plot range covers all data
        
        plt.xticks(rotation=spec.options.get("xtick_rotation", 0))

        # Add recession shading if requested and dates are available
        if spec.options.get("recession_shading", False) and min_date_overall and max_date_overall:
            highlight_recessions(ax, min_date_overall, max_date_overall, self.fred_service)

        # Legend handling
        handles, labels = ax.get_legend_handles_labels()
        if handles: # Only add legend if there are lines with labels
            # Position legend: if many items, put outside
            if len(datasets) > 4 and spec.options.get("legend_outside", True): # Default to True if many items
                ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), borderaxespad=0.)
                # Adjust layout to make room for legend outside
                plt.tight_layout(rect=spec.options.get("tight_layout_rect", [0, 0, 0.85, 1])) 
            else:
                ax.legend(loc=spec.options.get("legend_loc", "best"))
                plt.tight_layout() # Standard tight layout
        else:
            plt.tight_layout()


        ax.grid(spec.options.get("grid", True))
        
        # Source annotation
        source_text = spec.options.get("source_text")
        if source_text:
            plt.figtext(0.99, 0.01, source_text, ha='right', fontsize=8, fontstyle='italic', color='gray')
        elif spec.options.get("default_source_text", True): # Default to add FRED source
             plt.figtext(0.99, 0.01, "Source: FRED, Federal Reserve Bank of St. Louis", 
                    ha='right', fontsize=8, fontstyle='italic', color='gray')


        return fig

    def create_comparison_bar_chart(self, datasets: List[ProcessedDataset], spec: VisualizationSpec) -> plt.Figure:
        logger.warning("create_comparison_bar_chart is a placeholder and not implemented.")
        # Minimal placeholder figure
        fig, ax = plt.subplots(figsize=spec.options.get("figsize", (6,4)))
        ax.text(0.5, 0.5, "Comparison Bar Chart (Not Implemented)", ha='center', va='center')
        ax.set_title(spec.title or "Comparison Bar Chart")
        return fig

    def create_snapshot_value_display(self, datasets: List[ProcessedDataset], spec: VisualizationSpec) -> plt.Figure:
        logger.warning("create_snapshot_value_display is a placeholder and not implemented.")
        # Minimal placeholder figure
        fig, ax = plt.subplots(figsize=spec.options.get("figsize", (6,4)))
        ax.text(0.5, 0.5, "Snapshot Value Display (Not Implemented)", ha='center', va='center')
        ax.set_title(spec.title or "Snapshot Value Display")
        return fig

if __name__ == '__main__':
    import os
    if os.getenv("FRED_API_KEY"):
        try:
            fred_service_instance = FredService() # Requires FRED_API_KEY
            plotting_service = PlottingService(fred_service_instance)

            # Create Mock ProcessedDatasets
            ds1_points = [FredDataPoint(date="2020-01-01", value=100), FredDataPoint(date="2020-04-01", value=102), FredDataPoint(date="2022-01-01", value=110)]
            ds1_metadata = {"plot_label": "GDP (Billions)", "original_units": "Billions"} 
            dataset1 = ProcessedDataset(id="GDP_PROC", name="GDP Processed", data_points=ds1_points, metadata=ds1_metadata)
            
            ds2_points = [FredDataPoint(date="2020-01-01", value=5), FredDataPoint(date="2020-04-01", value=5.2), FredDataPoint(date="2022-01-01", value=4.5)]
            ds2_metadata = {"plot_label": "Unemployment (%)", "original_units": "Percent"}
            dataset2 = ProcessedDataset(id="UNEMP_PROC", name="Unemployment Processed", data_points=ds2_points, metadata=ds2_metadata)

            # Create VisualizationSpec for a line chart
            line_spec = VisualizationSpec(
                chart_type="line_chart",
                title="Economic Indicators Comparison",
                x_axis_label="Year", # More generic label
                y_axis_label="Value", # Y-axis will have different units
                data_ids=["GDP_PROC", "UNEMP_PROC"], 
                options={
                    "recession_shading": True,
                    "figsize": (12, 7),
                    "legend_loc": "best", # Let matplotlib decide initially
                    "legend_outside": True, # Test putting legend outside if many items
                    "default_source_text": True,
                    "tight_layout_rect": [0, 0, 0.83, 1] # Adjust for outside legend
                }
            )

            print("\n--- Test create_line_chart ---")
            fig = plotting_service.create_line_chart([dataset1, dataset2], line_spec)
            if fig:
                print(f"Figure created with title: {fig.axes[0].get_title()}")
                # To save or show locally:
                # fig.savefig("test_line_chart.png") 
                # print("Saved test_line_chart.png")
                # plt.show() # This will not work in a non-GUI environment.
                print("Plotting test completed, figure object created.")
            else:
                print("Figure creation returned None.")
        
        except ValueError as ve:
             print(f"ValueError during setup: {ve}")
        except Exception as e:
            print(f"Error during plotting test: {e}")
            logger.error("Error in plotting test", exc_info=True)

    else:
        print("FRED_API_KEY not set. Skipping PlottingService example usage.")
