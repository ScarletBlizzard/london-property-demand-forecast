-- Ожидается 33 района без пропусков индекса.
select count(*) as boroughs,
       count(distinct borough_code) as unique_codes,
       count(*) filter (where av_ptai_2015 is null) as missing_ai,
       min(av_ptai_2015) as min_ai,
       max(av_ptai_2015) as max_ai
from "primary".tfl__ptal_borough_2015;
