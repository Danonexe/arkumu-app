# CSV Mapping Editor - Template Hierarchy

This directory contains all templates for the CSV Mapping Editor interface. This README documents the template hierarchy and how they work together.

## 📁 Directory Structure

```
csv_mapping/
├── main_editor.html              # Main entry point
├── partials/                     # Reusable components
│   ├── main_content.html          # Primary content container
│   ├── mapping_workspace.html     # Right side workspace container
│   ├── table_content.html         # Left side datasets container
│   ├── selected_columns_workspace.html  # Workspace content
│   ├── dataset_workspace_section.html   # Individual dataset in workspace
│   ├── column_item.html           # Individual column in workspace
│   ├── dataset_card.html          # Individual dataset card (left side)
│   ├── column_badges.html         # Column selection badges
│   ├── table_rows.html            # Dataset table rows
│   ├── navbar_mapping_controls.html # Mapping save/load controls for navbar
│   └── [other partials...]
└── README.md                      # This file
```

## 🏗️ Template Hierarchy

### Level 1: Main Entry Point
```
main_editor.html
└── extends: base.html
    └── includes: partials/main_content.html
```

### Level 2: Main Content Layout
```
partials/main_content.html
├── Left Side: #table-content
│   └── includes: partials/table_content.html
└── Right Side: #mapping-workspace  
    └── includes: partials/mapping_workspace.html
```

### Level 3: Left Side (Datasets)
```
partials/table_content.html
└── for each selected dataset:
    └── includes: partials/dataset_card.html
        ├── Dataset Header
        ├── Column Badges Container: #column-badges-{dataset}
        │   └── includes: partials/column_badges.html
        └── Dataset Table Body
            └── includes: partials/table_rows.html
```

### Level 3: Right Side (Workspace)
```
partials/mapping_workspace.html
├── Tab Navigation (Workspace/JSON)
└── Tab Content: #tab-content
    └── Workspace Content: #workspace-content
        └── includes: partials/selected_columns_workspace.html
```

### Level 4: Workspace Organization
```
partials/selected_columns_workspace.html
├── Workspace Header (stats, clear button)
└── Workspace Container: #workspace-datasets-container
    └── for each dataset_group in datasets_with_columns (backend-sorted newest first):
        └── includes: partials/dataset_workspace_section.html
```

### Level 5: Dataset Sections in Workspace
```
partials/dataset_workspace_section.html
├── Collapsible Dataset Header
└── Dataset Columns Container
    └── for each column in dataset_group.columns (backend-sorted):
        └── includes: partials/column_item.html
```

### Level 6: Individual Components
```
partials/column_item.html
├── Column Information Display
├── Configuration Badges (FK, Multi-value, etc.)
└── Action Buttons (FK config, Remove, etc.)

partials/column_badges.html  
├── Individual Column Badges
├── "Add to Workspace" Button
└── "Select All/Deselect All" Button

partials/table_rows.html
└── Individual table rows for dataset preview

partials/navbar_mapping_controls.html
├── Current Mapping Save/Update Controls (when mapping exists)
├── View Graph Button (displays relationship graph modal)
├── View Overview Button (displays mapping text summary modal)
├── Save As New Mapping Controls
├── Load Existing Mapping Dropdown
└── Responsive 2x2 Grid Layout for Mobile/Desktop
```

## 🎯 Key HTMX Targets

| Target ID | Template | Purpose |
|-----------|----------|---------|
| `#main-content` | main_content.html | Full page refresh |
| `#table-content` | table_content.html | Left side datasets |
| `#mapping-workspace` | mapping_workspace.html | Right side workspace |
| `#workspace-content` | selected_columns_workspace.html | Workspace content |
| `#workspace-datasets-container` | selected_columns_workspace.html | Dataset sections container |
| `#tab-content` | mapping_workspace.html | Workspace/JSON tabs |
| `#column-badges-{dataset}` | column_badges.html | Column selection badges |
| `#dataset-{dataset}` | dataset_card.html | Individual dataset card |
| `#column-{column_id}` | column_item.html | Individual workspace column |
| `#save-feedback` | navbar_mapping_controls.html | Save operation feedback |
| `#load-mapping-select` | navbar_mapping_controls.html | Load mapping dropdown |
| `#mapping-status` | navbar_mapping_controls.html | Load operation status |
| `#mapping-graph-modal` | navbar_mapping_controls.html | Graph visualization modal target |
| `#mapping-overview-modal` | navbar_mapping_controls.html | Overview text summary modal target |

## 🔄 Data Flow

### Adding Columns to Workspace
1. User clicks column badge in `column_badges.html`
2. Updates `#column-badges-{dataset}` (left side)
3. User clicks "Add to Workspace" button
4. Updates `#workspace-content` (right side)
5. New columns appear at **TOP** of workspace (backend-sorted by timestamp)

### Removing Columns from Workspace  
1. User clicks ✕ button in `column_item.html`
2. Uses `hx-swap="delete"` to remove column element
3. Backend can send OOB updates to sync left side

### Mapping Save/Load Operations
1. **Saving Current Mapping**: User clicks "Save" in `navbar_mapping_controls.html`
2. **Save As New**: User enters name and clicks "Save As"
3. **Loading Mapping**: 
   - Dropdown auto-populates on page load via `hx-trigger="load"`
   - User selects mapping and clicks "Load" (with confirmation)
   - Updates `#mapping-status` with load results
4. **Dynamic Updates**: Save As triggers reload of mapping dropdown

### Graph Visualization
1. **View Graph**: User clicks "Graph" button in `navbar_mapping_controls.html`
2. **Graph Data Loading**: HTMX fetches graph data from `metadata:mapping_graph_data` endpoint
3. **Modal Display**: Graph data populates `#mapping-graph-modal` target
4. **Post-Save Integration**: Graph modal automatically displays after successful save operations

### Overview Text Summary
1. **View Overview**: User clicks "Overview" button in `navbar_mapping_controls.html`
2. **Overview Data Loading**: HTMX fetches mapping summary from `metadata:mapping_overview_data` endpoint
3. **Modal Display**: Text summary populates `#mapping-overview-modal` target
4. **Collapsible Structure**: Each dataset section is collapsible (collapsed by default) with quick stats badges
5. **Detailed Information**: Shows datasets, columns, anchors, foreign keys, external ontologies, multi-value columns, and junction tables

### Workspace Organization
- **Datasets**: Datasets with most recent workspace activity appear at TOP
  - Backend-sorted by latest `added_at` timestamp of any column in that dataset
  - Based on `workspace_columns` data, not `selected_datasets` browsing
  - Only datasets that actually have columns in workspace are shown
  - Uses `coordinator._prepare_datasets_with_columns()` with `reverse=True` sorting
- **Columns**: Within each dataset, preserves backend column ordering
  - Templates do NOT use `reversed` filter - rely on backend sorting
  - Column order determined by coordinator processing logic
- **No scrolling required** to see latest workspace additions
- **Workspace-centric**: Organized around actual mapping work, not browsing state

## 🎨 Styling Patterns

### DaisyUI Components Used
- `card` - Dataset cards and column items
- `collapse` - Collapsible dataset sections in workspace
- `badge` - Column selection and status badges
- `btn` - All interactive buttons
- `tabs` - Workspace/JSON view switcher
- `alert` - Column badges container

### Color Coding
- **Success/Green**: Dataset-related elements
- **Primary/Blue**: Selected columns and workspace elements  
- **Error/Red**: Remove/delete actions
- **Warning/Yellow**: Anchor columns
- **Info/Blue**: Relationship context
- **Accent**: Multi-value and action buttons

## 🔧 Recent Improvements

### State Preservation
- Removed complex JavaScript that was breaking JSON view
- Simplified HTMX targeting for better reliability
- Clean button implementations following HTMX best practices

### User Experience  
- **Newest items at top**: Both datasets and columns appear at top when added
- **No scroll jumping**: Interface stays in current position during operations
- **Clean targeting**: Uses reliable HTMX targets and swap methods

### Ordering & Sorting
- **Backend-driven ordering**: Removed template-level `reversed` filters
- **Timestamp-based sorting**: Uses `added_at` timestamps for proper chronological order
- **Coordinator-controlled**: All workspace ordering logic centralized in backend
- **Template transparency**: Templates preserve backend order without modification

### Error Handling
- Defensive HTMX targeting to avoid target errors
- Graceful fallbacks for missing elements
- Comprehensive error logging in main_editor.html
- Extensive coordinator and workspace logging for debugging

## 📝 Template Naming Convention

- **`main_*.html`**: Entry point templates
- **`partials/*.html`**: Reusable component templates
- **`*_content.html`**: Container/layout templates
- **`*_section.html`**: Individual section templates  
- **`*_item.html`**: Individual item templates
- **`*_badges.html`**: Badge/button collection templates

