# URI Generation in Arkumu Data Import: A Non-Technical Guide

## What are URIs and Why Do They Matter?

Think of URIs (Uniform Resource Identifiers) as unique digital addresses for every piece of information in your cultural heritage database. Just like every house needs a unique postal address, every piece of data in Arkumu gets a unique web address.

**Why this matters:**
- **Global uniqueness**: Your artwork, person, or event has a web address that works anywhere in the world
- **Data linking**: Other museums and databases can reference your data using these addresses
- **Future-proofing**: Your data becomes part of the global web of cultural heritage information
- **API access**: External applications can access specific pieces of your data using these addresses

## The URI Generation Process: Two Distinct Phases

The import process happens in **two separate phases** that create different types of URIs:

### Phase 1: Blueprint Creation (Schema Definition)
**When:** Before any actual data is processed
**Purpose:** Creates the "vocabulary" and structure for your data
**Think of it as:** Building the framework and rules before importing content

When you configure your mapping, the system immediately creates:

#### Dataset Container URIs
```
http://arkumu.org/data/your-museum/datasets/artworks-collection-2024
```
*This is like creating an empty folder labeled "Artworks Collection 2024"*

#### Entity Type URIs (What kinds of things exist)
```
http://arkumu.org/data/your-museum/types/artwork
http://arkumu.org/data/your-museum/types/person
```
*This defines that your data contains "artworks" and "people"*

#### Property URIs (What characteristics things can have)
```
http://arkumu.org/data/your-museum/properties/title
http://arkumu.org/data/your-museum/properties/artist
http://arkumu.org/data/your-museum/properties/date-created
```
*This defines that things in your data can have titles, artists, and creation dates*

**Important:** No actual data content is processed yet! This is just the structure.

---

### Phase 2: Actual Data Import (Content Creation)
**When:** After the blueprint exists and CSV data is processed
**Purpose:** Creates URIs for the actual content from your CSV files
**Think of it as:** Filling the pre-built structure with your actual artifacts, people, and events

**Your CSV Data:**
```csv
artwork_id,title,artist,date_created
A001,Mona Lisa,Leonardo da Vinci,1503
A002,Starry Night,Vincent van Gogh,1889
```

#### Individual Entity URIs (Your actual data items)
```
http://arkumu.org/data/your-museum/entities/artworks-collection-2024/A001
http://arkumu.org/data/your-museum/entities/artworks-collection-2024/A002
```
*These represent your specific artworks: the actual Mona Lisa and Starry Night*

#### Data Connections
Each entity gets both type and property connections:
- **Type Connection:** Entity is linked to its type via `rdf:type` relationship  
- **Property Values:** Entity gets properties like `title: "Mona Lisa"` using the pre-defined property URIs

## The Final Result: Linked Data

**After transformation:**
Your "Mona Lisa" entry becomes:
```
Entity: http://arkumu.org/data/your-museum/entities/artworks-collection-2024/A001
Type: http://arkumu.org/data/your-museum/types/artwork
Properties:
  - title: "Mona Lisa" (using http://arkumu.org/data/your-museum/properties/title)
  - artist: "Leonardo da Vinci" (using http://arkumu.org/data/your-museum/properties/artist)
  - date-created: "1503" (using http://arkumu.org/data/your-museum/properties/date-created)
```

## Understanding the Namespace System

The system organizes URIs into different "neighborhoods" based on what they represent:

### `/datasets/` - Data Collections
**Purpose:** Containers for your data collections
**Example:** `http://arkumu.org/data/louvre/datasets/paintings-collection`
**What it represents:** The entire paintings collection from the Louvre

### `/entities/` - Individual Items
**Purpose:** Specific objects, people, events, or concepts
**Example:** `http://arkumu.org/data/louvre/entities/paintings-collection/ML001`
**What it represents:** A specific painting with ID ML001

### `/types/` - Categories of Things
**Purpose:** Classifications or categories
**Example:** `http://arkumu.org/data/louvre/types/oil-painting`
**What it represents:** The concept of "oil painting" as a category

### `/properties/` - Characteristics and Relationships
**Purpose:** Attributes that describe entities
**Example:** `http://arkumu.org/data/louvre/properties/creation-date`
**What it represents:** The property of "when something was created"

## Visual Comparison: Blueprint vs Import

| What Gets Created | Blueprint Phase | Import Phase |
|------------------|----------------|--------------|
| **Purpose** | Structure & vocabulary | Actual content |
| **Timing** | When you configure mapping | When CSV data is processed |
| **URIs Created** | Types, Properties, Datasets | Individual entities |
| **Analogy** | Building the library shelves | Placing books on shelves |

## Real-World Example: Museum Exhibition Import

Let's follow a complete example showing both phases:

### Your Original CSV Data:
```csv
exhibition_id,name,curator,start_date,venue
EX001,Impressionist Masters,Dr. Marie Dubois,2024-03-15,Gallery A
EX002,Ancient Sculptures,Prof. James Wilson,2024-06-01,Sculpture Hall
```

### Phase 1: Blueprint Creation (Happens First)
**When:** As soon as you configure your data mapping
**Creates the schema:**

#### Dataset Container:
```
http://arkumu.org/data/met-museum/datasets/exhibitions-2024
```
*"I will have a collection called exhibitions-2024"*

#### Entity Type:
```
http://arkumu.org/data/met-museum/types/exhibition
```
*"Things in this collection are 'exhibitions'"*

#### Property Vocabulary:
```
http://arkumu.org/data/met-museum/properties/name
http://arkumu.org/data/met-museum/properties/curator
http://arkumu.org/data/met-museum/properties/start-date
http://arkumu.org/data/met-museum/properties/venue
```
*"Exhibitions can have names, curators, start dates, and venues"*

**Result:** The system now "knows" what an exhibition is and what properties it can have.

---

### Phase 2: Data Import (Happens Second)
**When:** Your CSV data is actually processed
**Creates the content:**

#### Individual Exhibition Entities:
```
http://arkumu.org/data/met-museum/entities/exhibitions-2024/EX001
http://arkumu.org/data/met-museum/entities/exhibitions-2024/EX002
```

#### With Their Specific Data:
**Exhibition EX001:**
- **Type:** `http://arkumu.org/data/met-museum/types/exhibition` (via `rdf:type`)
- Name: "Impressionist Masters" (using `properties/name`)
- Curator: "Dr. Marie Dubois" (using `properties/curator`)
- Start Date: "2024-03-15" (using `properties/start-date`)
- Venue: "Gallery A" (using `properties/venue`)

**Exhibition EX002:**
- **Type:** `http://arkumu.org/data/met-museum/types/exhibition` (via `rdf:type`)
- Name: "Ancient Sculptures" (using `properties/name`)
- Curator: "Prof. James Wilson" (using `properties/curator`)
- Start Date: "2024-06-01" (using `properties/start-date`)
- Venue: "Sculpture Hall" (using `properties/venue`)

### The Magic: How Data Transforms

**Before (Traditional Database):**
- Exhibition EX001 exists only in your database
- No way for external systems to reference it
- Data is isolated

**After (Linked Data with URIs):**
- Exhibition EX001 has a global web address
- Other museums can link to your exhibition
- Researchers can cite it directly
- APIs can fetch specific exhibition details
- Your data becomes part of the global cultural knowledge graph

## Benefits for Your Institution

### 1. **Data Discoverability**
Your collections become findable through web search and academic databases.

### 2. **Collaboration Opportunities**
Other institutions can easily reference and link to your data for joint exhibitions or research.

### 3. **API-First Architecture**
External applications can directly access specific pieces of your data using the URIs.

### 4. **Future-Proof Data**
Your data structure follows international standards, ensuring long-term accessibility.

### 5. **Rich Data Connections**
Link your artworks to artist biographies, historical events, or related works in other collections.

## Technical Implementation Notes

The URI generation process is handled automatically by the Arkumu import system:

1. **Mapping Configuration**: You define how your CSV columns map to semantic properties
2. **Automatic Processing**: The system generates all URIs during import
3. **Namespace Management**: URIs are organized into logical namespaces
4. **Conflict Resolution**: Duplicate handling ensures unique addresses
5. **Validation**: All URIs follow international standards

## Key Differences: Blueprint vs Import

### Blueprint Phase (Schema-First)
- **Triggered by:** Saving your data mapping configuration
- **Speed:** Very fast (no CSV processing)
- **Creates:** The "vocabulary" for your data
- **Purpose:** Defines what types of things exist and what properties they can have
- **Connections:** Links datasets to entity types, entity types to properties
- **Reusable:** One blueprint can support multiple CSV imports

### Import Phase (Data Processing)
- **Triggered by:** Running the actual import with CSV files
- **Speed:** Slower (processes every row of data)
- **Creates:** Individual entities from your CSV rows
- **Purpose:** Transforms your spreadsheet data into linked data entities
- **Connections:** Links entities to their property values
- **Scalable:** Can process thousands of rows using the pre-built blueprint

## Complete Semantic Connections

**The system now creates full semantic connections between all phases:**

### All Connections Implemented:
✅ **Dataset** ↔ **Entity Type** (via `defines_entity_type`)  
✅ **Entity Type** ↔ **Properties** (via `defines_property`)  
✅ **Entity** ↔ **Property Values** (via property URIs)  
✅ **Entity** ↔ **Entity Type** (via `rdf:type` relationships)

This means:
- **Type URIs are created** in `/types/` namespace during blueprint phase
- **Entity URIs are created** in `/entities/` namespace during import phase  
- **Entities are explicitly linked** to their types via standard `rdf:type` relationships

### Benefits:
- Entities are formally declared to be of a specific type
- Full RDF/LOD semantics are realized
- Enables powerful queries like "find all entities of type X"
- Compatible with standard RDF tools and SPARQL queries

## Common Questions

**Q: Do I need to understand URIs to use the system?**
A: No! The system generates them automatically. This guide helps you understand what happens behind the scenes.

**Q: Can I customize the URI structure?**
A: The base structure follows standards, but institution identifiers and dataset names can be customized.

**Q: What happens if I re-import data?**
A: The system maintains consistent URIs, so your data addresses remain stable over time. The blueprint stays the same, only the entity data gets updated.

**Q: Why are there two phases?**
A: This "schema-first" approach is much more efficient. The blueprint is created once and reused for all imports, making subsequent data processing faster and more consistent.

**Q: What if I change my mapping?**
A: Changing the mapping creates a new blueprint, which might result in different URI structures for new imports.

**Q: How do URIs help with data quality?**
A: URIs make data relationships explicit, helping identify inconsistencies and improving data quality.

---

*This guide provides a conceptual overview of URI generation in Arkumu. For technical implementation details, consult the developer documentation.*