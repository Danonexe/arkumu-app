import pytest


@pytest.mark.django_db
def test_investigate_all_constraints():
    """Check what constraints actually exist on the metadata_resource table."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Get all constraints on metadata_resource table
        cursor.execute("""
            SELECT 
                c.conname as constraint_name,
                c.contype as constraint_type,
                array_agg(a.attname ORDER BY a.attnum) as column_names,
                pg_get_constraintdef(c.oid) as constraint_definition
            FROM pg_constraint c
            JOIN pg_class t ON c.conrelid = t.oid
            JOIN pg_namespace n ON t.relnamespace = n.oid
            LEFT JOIN pg_attribute a ON c.conrelid = a.attrelid AND a.attnum = ANY(c.conkey)
            WHERE t.relname = 'metadata_resource' 
            AND n.nspname = 'public'
            GROUP BY c.conname, c.contype, c.oid, pg_get_constraintdef(c.oid)
            ORDER BY c.conname;
        """)
        constraints = cursor.fetchall()
        
        print(f"\n=== All constraints on metadata_resource table ===")
        print(f"Found {len(constraints)} constraints:")
        
        for constraint in constraints:
            name, ctype, columns, definition = constraint
            type_desc = {
                'p': 'PRIMARY KEY',
                'u': 'UNIQUE',
                'c': 'CHECK',
                'f': 'FOREIGN KEY'
            }.get(ctype, ctype)
            
            print(f"\n  {name} ({type_desc})")
            print(f"    Columns: {columns}")
            print(f"    Definition: {definition}")
        
        # Check specifically for literal-related constraints
        literal_constraints = [c for c in constraints if 'literal' in c[0].lower() or 'value' in c[0].lower()]
        print(f"\n=== Literal/Value related constraints ===")
        print(f"Found {len(literal_constraints)} literal-related constraints:")
        for constraint in literal_constraints:
            print(f"  - {constraint[0]}")
        
        # Check if the expected constraint is missing
        expected_constraint = 'unique_literal_value_hash'
        constraint_names = [c[0] for c in constraints]
        if expected_constraint not in constraint_names:
            print(f"\n⚠️  MISSING: Expected constraint '{expected_constraint}' not found!")
            print(f"   This explains why duplicate literals are being created.")
        else:
            print(f"\n✓ Found expected constraint: {expected_constraint}")


@pytest.mark.django_db  
def test_check_table_structure():
    """Check the actual table structure to see what fields exist."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                column_name, 
                data_type, 
                is_nullable,
                column_default
            FROM information_schema.columns 
            WHERE table_name = 'metadata_resource' 
            AND table_schema = 'public'
            ORDER BY ordinal_position;
        """)
        columns = cursor.fetchall()
        
        print(f"\n=== metadata_resource table structure ===")
        print(f"Found {len(columns)} columns:")
        
        for column in columns:
            name, dtype, nullable, default = column
            print(f"  {name:20} {dtype:15} {'NULL' if nullable == 'YES' else 'NOT NULL':8} {default or ''}")
        
        # Check for expected constraint fields
        expected_fields = ['value_hash', 'value', 'datatype', 'language', 'name']
        column_names = [c[0] for c in columns]
        
        print(f"\n=== Constraint field check ===")
        for field in expected_fields:
            if field in column_names:
                print(f"  ✓ {field} - exists")
            else:
                print(f"  ✗ {field} - MISSING!")


@pytest.mark.django_db
def test_migration_status():
    """Check which migrations have been applied."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT app, name, applied 
            FROM django_migrations 
            WHERE app = 'metadata'
            ORDER BY applied;
        """)
        migrations = cursor.fetchall()
        
        print(f"\n=== Applied metadata migrations ===")
        print(f"Found {len(migrations)} migrations:")
        
        for migration in migrations:
            app, name, applied = migration
            print(f"  {applied} - {name}")
        
        # Look for recent migration that might contain the constraint
        recent_migrations = [m for m in migrations if '0001_initial' in m[1] or '0002_initial' in m[1]]
        print(f"\n=== Recent initial migrations ===")
        for migration in recent_migrations:
            print(f"  {migration[2]} - {migration[1]}")