# Home Assistant integration for EyeOnWater service

1. Follow [instruction](https://hacs.xyz/docs/faq/custom_repositories/) for adding a custom git repository to your HA.

Add `https://github.com/kdeyev/eyeonwater` as Repository and select the `Integration` category.

![add-repository](img/add-repository.png)

1. Add EyeOnWater integration following [HACS instructions](https://github.com/hacs/integration)

Follow the configuration dialog and use your username and password, which you use to log in on eyeonwater.

![configuration](img/configuration.png)

1. Configure integration options by clicking "Options" on the integration card:

The integration uses some of your HA configurations:

- `Country` is used for identification if `eyeonwater.ca` should be used.
- `Unit System` is used for switching between Metric and US customary measurement systems
- `Use unified sensor` toggle allows you to choose between a single sensor per meter or multiple sensors (consumption, consumption today, etc.)

![options](img/options.png)

1. After successful initialization you should see the integration card appear:

![integration-card](img/integration-card.png)

![watermeter](img/watermeter.png)

![watermeter-graph](img/watermeter-graph.png)

1. Got to `Settings`->`Dashboards`->`Energy` configuration.

You should be able to choose your water meter in the Water Consumption.

Pay attention that you will see 2 different meters, please choose that one that ending with "Statistics".

![image](https://github.com/user-attachments/assets/fb521562-22e9-407e-9796-13a422e36e6b)

You may see an error message like: `The state class '' of this entity is not supported.` It's expected, for more details please look at <https://github.com/kdeyev/eyeonwater/issues/30>

1. Have fun and watch your utilities in the Energy Dashboard.

![energy-dashboard](img/energy-dashboard.png)

Pay attention that EyeOnWater publishes the meter reading once in several hours (even when they accumulate the meter reading once in several minutes). So data may come with a delay of several hours.

## Import historical data

The integration allows to import of historical water data usage after it was installed.

- Go to `Developer Tools` -> Servies`.
- Enter the `EyeOnWater: import_historical_data` service name.
- Choose how many days of historical data you want to import.
- Pay attention that the import may take some time.

![import-historical-data](img/import-historical-data.png)

## Unsupported state class

Please pay attention: If you look at the `Developer Tools` -> `Statistics`, you will see an error message associated with the water sensor:

```text
The state class '' of this entity is not supported.
```

or

```text
Unsupported state class
The state class of this entity, is not supported.
Statistics cannot be generated until this entity has a supported state class.

If this state class was provided by an integration, this is a bug. Please report an issue.

If you have set this state class yourself, please correct it. The different state classes and when to use which can be found in the developer documentation. If the state class has permanently changed, you may want to remove the long term statistics of it from your database.

Do you want to permanently remove the long term statistics of sensor.water_meter_200010108 from your database?
```

It's a side-effect of the way we prevent the HA from recalculating the sensor statistics. You can find more information [in issue #30](https://github.com/kdeyev/eyeonwater/issues/30)
