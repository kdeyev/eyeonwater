# EyeOnWater Test Suite

Comprehensive test suite for the EyeOnWater Home Assistant integration.

## Test Coverage

### Unit Tests

#### `test_const.py`

- Constants validation
- Service names
- Configuration defaults
- Timeout settings

#### `test_statistic_helper.py`

- Unit conversion (GAL, CF, CM)
- ID normalization
- Statistic metadata generation
- Data conversion logic
- Cumulative sum calculations
- Continuity with existing data

#### `test_statistics_tools.py`

- Statistic ID resolution
- Monotonic violation detection
- Priority ordering of ID parameters

#### `test_coordinator.py`

- `EyeOnWaterData` class import and existence
- `setup()` and `read_meters()` method presence
- Both methods verified as `async def` (coroutine functions)

#### `test_sensor.py`

- Sensor class imports and existence (`EyeOnWaterUnifiedSensor`, `EyeOnWaterTempSensor`)
- `_attr_state_class = TOTAL_INCREASING` — required for Energy Dashboard cost calculation
- `_attr_device_class = WATER` — required for Energy Dashboard water source picker
- `_attr_should_poll = False` — sensor uses coordinator push, never HA polling
- `_attr_has_entity_name = False` — preserves standalone entity name
- `EyeOnWaterTempSensor` device class, unit of measurement, and poll behaviour

### Integration Tests

#### `test_integration.py`

- End-to-end data flow
- API → Statistics pipeline
- Data filtering logic
- Multiple meter scenarios
- Timezone handling
- Error recovery

#### `test_config_flow.py`

- `config_flow` module import
- `ConfigFlow` class existence

### Performance Tests

#### `test_performance.py`

- Large dataset handling (1+ year hourly data)
- High-frequency data (15-minute intervals)
- Memory efficiency
- Stress scenarios
- Large consumption jumps
- Floating point precision

#### `test_edge_cases.py`

- Boundary conditions
- Empty/invalid inputs
- DST transitions
- Year boundaries
- Leap years
- Out-of-order timestamps
- Duplicate data
- Unicode characters

### Import Tests

#### `test_imports.py`

- Module import validation
- Dependency availability
- Home Assistant imports

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_statistic_helper.py
```

### Run Specific Test Class

```bash
pytest tests/test_statistic_helper.py::TestUnitConversion
```

### Run Specific Test

```bash
pytest tests/test_statistic_helper.py::TestUnitConversion::test_convert_gallons
```

### Run with Coverage

```bash
pytest --cov=custom_components.eyeonwater --cov-report=html
```

### Run with Verbose Output

```bash
pytest -v
```

### Run Only Fast Tests (skip slow performance tests)

```bash
pytest -m "not slow"
```

## Test Fixtures

Common fixtures available in `conftest.py`:

- `mock_hass`: Mock Home Assistant instance
- `mock_client`: Mock pyonwater Client
- `mock_meter`: Mock Meter with sample data
- `sample_datapoints`: Sample DataPoint sequence
- `mock_recorder`: Mock recorder instance
- `mock_config_entry`: Mock config entry

## Test Organization

```bash
tests/
├── conftest.py              # Shared fixtures
├── test_const.py            # Constants tests
├── test_statistic_helper.py # Core statistics logic
├── test_statistics_tools.py # Statistics utilities
├── test_coordinator.py      # Coordinator tests
├── test_sensor.py           # Sensor entity tests
├── test_integration.py      # End-to-end tests
├── test_config_flow.py      # Configuration flow
├── test_performance.py      # Performance tests
├── test_edge_cases.py       # Edge cases and boundaries
└── test_imports.py          # Import validation
```

## Coverage Goals

- **Unit Tests**: Test individual functions and classes in isolation
- **Integration Tests**: Test component interactions and data flow
- **Performance Tests**: Validate behavior with realistic data volumes
- **Edge Cases**: Ensure robustness with unusual inputs

## Key Test Scenarios

### Data Conversion

- ✅ Empty data handling
- ✅ Single data point
- ✅ Multiple data points
- ✅ Continuity with existing statistics
- ✅ Monotonic enforcement
- ✅ Large datasets (8760+ points)

### Unit Conversion

- ✅ Gallons (GAL)
- ✅ Cubic Feet (CF)
- ✅ Cubic Meters (CM)
- ✅ Unrecognized units

### ID Normalization

- ✅ Alphanumeric IDs
- ✅ Special characters
- ✅ Uppercase conversion
- ✅ Space replacement

### Error Handling

- ✅ Empty data handling (no panic on zero-length input)
- ✅ Single data point (degenerate dataset)
- ✅ Unrecognized units raise `UnrecognizedUnitError`
- ✅ None continuity params handled gracefully
- ✅ Input data not mutated by conversion
- ⚠️ Authentication errors, API failures, network errors — requires HA infrastructure; not yet covered

### Timezone Handling

- ✅ Timezone preservation
- ✅ DST transitions
- ✅ Year boundaries
- ✅ Leap years

## Contributing

When adding new functionality:

1. Write tests first (TDD approach recommended)
2. Ensure all existing tests pass
3. Add new test cases for edge cases
4. Update this README if adding new test files
5. Run coverage report to identify gaps

## Dependencies

Test dependencies are managed in `pyproject.toml`:

```toml
[tool.poetry.group.dev.dependencies]
pytest = "*"
pytest-asyncio = "*"
pytest-cov = "*"
pytest-homeassistant-custom-component = "*"
```

## VS Code Integration

Tests are configured to work with VS Code Test Explorer:

- Tests auto-discover on workspace load
- Click play button to run individual tests
- View results inline in editor
- Debug tests with breakpoints

## Notes

- Some tests require Home Assistant core components (mocked in fixtures)
- Async tests use `pytest-asyncio` plugin
- Performance tests may take longer to run
- Mock data uses realistic values from Eye On Water API
