# Every query shown on the DBMS Demonstration page. Read-only SELECTs only.
# Entry format: (title, concept, explanation, SQL)

_RAW = [
    ('Filter and sort available phones',
     'SELECT, WHERE, ORDER BY',
     'WHERE keeps only rows that satisfy the condition and ORDER BY sorts what is left. The query reads the AvailableListings view, so only approved listings can appear.',
     '''SELECT listing_id, brand, model_name, asking_price
        FROM AvailableListings
        WHERE device_category = 'Mobile Phone'
        ORDER BY asking_price DESC'''),

    ('Device, model and owner',
     'INNER JOIN across three tables',
     'INNER JOIN returns only rows that have a match in both tables. Each device is joined to its model and to its owner.',
     '''SELECT D.device_id, DM.brand, DM.model_name, U.full_name AS owner
        FROM Devices D
        INNER JOIN DeviceModels DM ON D.model_id = DM.model_id
        INNER JOIN Users U ON D.owner_id = U.user_id
        ORDER BY D.device_id'''),

    ('Users who own no device',
     'LEFT OUTER JOIN with IS NULL',
     'LEFT JOIN keeps every user even without a matching device. Unmatched rows carry NULL in the device columns, and IS NULL isolates them.',
     '''SELECT U.user_id, U.full_name
        FROM Users U
        LEFT JOIN Devices D ON U.user_id = D.owner_id
        WHERE D.device_id IS NULL'''),

    ('Models nobody has registered',
     'RIGHT OUTER JOIN with IS NULL',
     'RIGHT JOIN keeps every row of the right table, DeviceModels. Models with no matching device show NULL in the device column. Foreign keys prevent orphan devices, so the unmatched side here is the model.',
     '''SELECT DM.brand, DM.model_name, D.device_id
        FROM Devices D
        RIGHT JOIN DeviceModels DM ON D.model_id = DM.model_id
        WHERE D.device_id IS NULL'''),

    ('All users and all devices',
     'FULL OUTER JOIN simulated with LEFT JOIN, RIGHT JOIN and UNION',
     'MySQL has no FULL OUTER JOIN keyword. A LEFT JOIN and a RIGHT JOIN combined with UNION give the same result, and UNION removes the duplicated matched rows.',
     '''SELECT U.full_name, D.device_id
        FROM Users U LEFT JOIN Devices D ON U.user_id = D.owner_id
        UNION
        SELECT U.full_name, D.device_id
        FROM Users U RIGHT JOIN Devices D ON U.user_id = D.owner_id'''),

    ('Every category with every listing type',
     'CROSS JOIN (Cartesian product)',
     'CROSS JOIN pairs every row of one set with every row of the other: 5 categories x 2 listing types = 10 rows.',
     '''SELECT c.device_category, t.listing_type
        FROM (SELECT DISTINCT device_category FROM DeviceModels) c
        CROSS JOIN (SELECT DISTINCT listing_type FROM Listings) t
        ORDER BY c.device_category'''),

    ('Devices per category',
     'GROUP BY with COUNT()',
     'GROUP BY collapses the rows into one row per category and COUNT counts the rows in each group.',
     '''SELECT DM.device_category, COUNT(*) AS devices
        FROM Devices D
        JOIN DeviceModels DM ON D.model_id = DM.model_id
        GROUP BY DM.device_category'''),

    ('Categories with at least two listings',
     'HAVING',
     'WHERE filters rows before grouping; HAVING filters the groups after aggregation.',
     '''SELECT DM.device_category, COUNT(*) AS listings
        FROM Listings L
        JOIN Devices D ON L.device_id = D.device_id
        JOIN DeviceModels DM ON D.model_id = DM.model_id
        GROUP BY DM.device_category
        HAVING COUNT(*) >= 2'''),

    ('Revenue from completed sales',
     'SUM() and COUNT()',
     'SUM adds up the final price of every completed transaction.',
     '''SELECT COUNT(*) AS completed_sales, SUM(final_price) AS revenue
        FROM Transactions
        WHERE transaction_status IN ('Completed')'''),

    ('Average asking price of live listings',
     'AVG()',
     'AVG returns the mean asking price of the approved listings.',
     '''SELECT ROUND(AVG(asking_price), 2) AS average_price
        FROM Listings
        WHERE listing_status IN ('Available')'''),

    ('Listings priced above the average',
     'Nested query (subquery)',
     'The inner query computes one number, the average asking price. The outer query keeps the listings above it.',
     '''SELECT listing_id, asking_price
        FROM Listings
        WHERE asking_price > (SELECT AVG(asking_price) FROM Listings)
        ORDER BY asking_price DESC'''),

    ('Users who submitted e-waste',
     'EXISTS (correlated subquery)',
     'EXISTS is true as soon as the inner query finds one matching row, so it never has to count them all.',
     '''SELECT U.user_id, U.full_name
        FROM Users U
        WHERE EXISTS (SELECT 1 FROM EwasteRecords E WHERE E.reported_by = U.user_id)'''),

    ('Everyone who sold or bought',
     'UNION',
     'UNION stacks two result sets that have the same number and type of columns and removes duplicates.',
     '''SELECT U.full_name, 'Seller' AS role_in_deal
        FROM Users U
        JOIN Devices D ON U.user_id = D.owner_id
        JOIN Listings L ON D.device_id = L.device_id
        WHERE L.listing_status = 'Sold'
        UNION
        SELECT U.full_name, 'Buyer'
        FROM Users U
        JOIN Transactions T ON U.user_id = T.buyer_id
        WHERE T.transaction_status IN ('Completed')'''),

    ('Sales and revenue per category',
     'Four-table JOIN with GROUP BY and SUM()',
     'Follows the chain Transactions, Listings, Devices, DeviceModels so that revenue can be grouped by a column four tables away.',
     '''SELECT DM.device_category, COUNT(*) AS sales, SUM(T.final_price) AS revenue
        FROM Transactions T
        JOIN Listings L ON T.listing_id = L.listing_id
        JOIN Devices D ON L.device_id = D.device_id
        JOIN DeviceModels DM ON D.model_id = DM.model_id
        WHERE T.transaction_status IN ('Completed')
        GROUP BY DM.device_category'''),

    ('Listings flagged as overpriced',
     'View with a CASE expression',
     'PriceCheck is a saved query. It estimates a fair value from the model reference price and the years of use, and a CASE expression turns the comparison into a flag the admin can act on.',
     '''SELECT listing_id, listing_status, brand, model_name,
               asking_price, estimated_value, price_flag
        FROM PriceCheck
        WHERE price_flag IN ('Overpriced')
        ORDER BY listing_id'''),

    ('E-waste by recycling status',
     'GROUP BY on a status column',
     'Counts the e-waste records at each stage of the recycling pipeline.',
     '''SELECT recycling_status, COUNT(*) AS records
        FROM EwasteRecords
        GROUP BY recycling_status'''),

    ('E-waste items with their device, if any',
     'LEFT JOIN on a nullable foreign key with COALESCE',
     'Standalone items have device_id NULL, so an INNER JOIN would drop them. LEFT JOIN keeps them and COALESCE picks the item name when there is no device.',
     '''SELECT E.ewaste_id,
               COALESCE(E.item_name, CONCAT(DM.brand, ' ', DM.model_name)) AS item,
               E.item_type, E.recycling_status
        FROM EwasteRecords E
        LEFT JOIN Devices D ON E.device_id = D.device_id
        LEFT JOIN DeviceModels DM ON D.model_id = DM.model_id
        ORDER BY E.ewaste_id'''),
]

DEMO_QUERIES = [
    {'title': t, 'concept': c, 'explanation': e, 'sql': s}
    for t, c, e, s in _RAW
]